"""Ranker: pulls Search Console rows into `rankings`, then looks for drops — and ties a drop to
a recently verified change set so a bad fix is caught, not just noticed."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select

from app.agents.base import AgentContext
from app.db.base import utcnow
from app.db.models import Change, ChangeSet, Keyword, Page, Ranking, Site
from app.keywords.analyze import position_delta

GSC_LAG_DAYS = 2  # Search Console data is final ~2 days behind


class RankerAgent:
    name = "ranker"
    handles = ("rank.sync",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        site_id = uuid.UUID(payload["site_id"])
        gsc = ctx.integrations.gsc
        async with ctx.session() as s:
            site = await s.get(Site, site_id)
            if not site:
                raise RuntimeError(f"Site {site_id} not found")
            if not gsc.enabled or not site.gsc_property:
                await ctx.emit("warn", "Search Console not configured for this site; skipping rank sync", session=s)
                await s.commit()
                return {"skipped": True}
            have_any = await s.scalar(select(func.count()).select_from(Ranking).where(Ranking.site_id == site_id))
            prop, threshold = site.gsc_property, int((site.settings or {}).get("rank_drop_threshold", 3))

        end = date.today() - timedelta(days=GSC_LAG_DAYS)
        days = int(payload.get("days") or (90 if not have_any else 3))
        start = end - timedelta(days=days)
        rows = await gsc.query_analytics(prop, start.isoformat(), end.isoformat())
        await ctx.emit("info", f"Fetched {len(rows)} Search Console rows for {start}..{end}")

        inserted = 0
        async with ctx.session() as s:
            kws = {k.term: k for k in (await s.scalars(select(Keyword).where(Keyword.site_id == site_id))).all()}
            existing = {
                (kid, url, d)
                for kid, url, d in (
                    await s.execute(select(Ranking.keyword_id, Ranking.page_url, Ranking.day).where(Ranking.site_id == site_id, Ranking.day >= start))
                ).all()
            }
            for r in rows:
                term = r.query.strip().lower()
                if not term:
                    continue
                k = kws.get(term)
                if k is None:
                    k = Keyword(site_id=site_id, term=term, source="gsc")
                    s.add(k)
                    await s.flush()
                    kws[term] = k
                d = date.fromisoformat(r.day)
                key = (k.id, r.page, d)
                if key in existing:
                    continue
                s.add(
                    Ranking(
                        site_id=site_id, keyword_id=k.id, page_url=r.page, day=d, position=r.position, clicks=r.clicks, impressions=r.impressions, ctr=r.ctr
                    )
                )
                existing.add(key)
                inserted += 1
            await s.commit()

        drops = await self._detect_drops(ctx, site_id, threshold)
        await ctx.emit("info", f"Rank sync done: {inserted} new rows, {len(drops)} drops ≥ {threshold} positions", {"drops": drops[:20]})
        return {"rows": len(rows), "inserted": inserted, "drops": len(drops)}

    async def _detect_drops(self, ctx: AgentContext, site_id: uuid.UUID, threshold: int) -> list[dict[str, Any]]:
        since = date.today() - timedelta(days=30)
        async with ctx.session() as s:
            data = (
                await s.execute(
                    select(Keyword.id, Keyword.term, Keyword.tracked, Ranking.page_url, Ranking.day, Ranking.position, Ranking.impressions)
                    .join(Ranking, Ranking.keyword_id == Keyword.id)
                    .where(Ranking.site_id == site_id, Ranking.day >= since)
                )
            ).all()
            series: dict[tuple[uuid.UUID, str, bool, str], list[tuple[str, float, int]]] = defaultdict(list)
            for kid, term, tracked, url, day, pos, imp in data:
                series[(kid, term, tracked, url)].append((day.isoformat(), pos, imp))

            # keywords that matter: tracked, or in the top 50 by impressions
            volume = sorted(series.items(), key=lambda kv: -sum(x[2] for x in kv[1]))
            watch = [kv for kv in volume if kv[0][2]] + [kv for kv in volume[:50] if not kv[0][2]]

            recent_cs = (
                await s.execute(
                    select(ChangeSet.id, Page.url)
                    .join(Change, Change.change_set_id == ChangeSet.id)
                    .join(Page, Page.id == Change.page_id)
                    .where(ChangeSet.site_id == site_id, ChangeSet.status == "verified", ChangeSet.decided_at >= utcnow() - timedelta(days=21))
                )
            ).all()
            cs_by_url: dict[str, set[uuid.UUID]] = defaultdict(set)
            for cs_id, url in recent_cs:
                cs_by_url[url].add(cs_id)

            drops: list[dict[str, Any]] = []
            for (_kid, term, _tracked, url), pts in watch:
                d = position_delta(pts)
                if d is None or d.delta < threshold:
                    continue
                suspects = sorted(str(x) for x in cs_by_url.get(url, ()))
                drop = {"keyword": term, "page": url, "from": d.baseline, "to": d.recent, "delta": d.delta, "suspect_change_sets": suspects}
                drops.append(drop)
                await ctx.emit(
                    "error" if suspects else "warn",
                    f'"{term}" dropped {d.delta} positions ({d.baseline} → {d.recent}) on {url}'
                    + (" after a recent change set — review for rollback" if suspects else ""),
                    drop,
                    session=s,
                )
            await s.commit()
        return drops
