"""Keyword Scout: turns Search Console data into an opportunity-ranked keyword list, a focus
keyword per page, and (LLM on) intent labels + new terms. Hands off to the Fixer."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select

from app.agents.base import AgentContext
from app.db.base import utcnow
from app.db.models import Keyword, Page, Ranking, Site
from app.keywords.analyze import RankRow, aggregate_queries, choose_focus_keywords
from app.util.urls import canon, safe_path


class IntentLabel(BaseModel):
    query: str
    intent: Literal["informational", "navigational", "transactional", "commercial"]


class NewTerm(BaseModel):
    term: str
    target_path: str
    why: str


class Suggestions(BaseModel):
    intents: list[IntentLabel]
    new_terms: list[NewTerm]


class KeywordScoutAgent:
    name = "keyword-scout"
    handles = ("keywords.scout",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        site_id = uuid.UUID(payload["site_id"])
        since = (utcnow() - timedelta(days=28)).date()

        async with ctx.session() as s:
            site = await s.get(Site, site_id)
            if not site:
                raise RuntimeError(f"Site {site_id} not found")
            rows = (
                await s.execute(
                    select(Keyword.term, Ranking.page_url, Ranking.position, Ranking.clicks, Ranking.impressions)
                    .join(Keyword, Keyword.id == Ranking.keyword_id)
                    .where(Ranking.site_id == site_id, Ranking.day >= since)
                )
            ).all()
            if not rows:
                await ctx.emit("warn", "No Search Console data in the last 28 days; run rank.sync first. Proposing fixes from on-page signals only.")
                await ctx.handoff("fix.propose", {"site_id": str(site_id), "crawl_id": payload.get("crawl_id")})
                return {"queries": 0, "focus_assigned": 0}

            stats = aggregate_queries(RankRow(t, p, pos, c, i) for t, p, pos, c, i in rows)
            pages = (await s.execute(select(Page.id, Page.url, Page.path).where(Page.site_id == site_id))).all()
            page_by_url = {canon(u): (pid, path) for pid, u, path in pages}

            def path_of(url: str) -> str:
                hit = page_by_url.get(canon(url))
                return hit[1] if hit else safe_path(url)

            kw_rows = {k.term: k for k in (await s.scalars(select(Keyword).where(Keyword.site_id == site_id))).all()}
            for st in stats:
                k = kw_rows.get(st.query)
                if k is None:
                    continue
                hit = page_by_url.get(canon(st.best_page))
                k.opportunity, k.bucket, k.target_page_id = st.opportunity, st.bucket, (hit[0] if hit else None)

            settings = dict(site.settings or {})
            before: dict[str, str] = dict(settings.get("focus_keywords", {}))
            focus = choose_focus_keywords(stats, before, path_of)
            assigned = len(focus) - len(before)
            if assigned:
                settings["focus_keywords"] = focus
                site.settings = settings

            suggested = 0
            if ctx.integrations.llm.enabled:
                try:
                    res = await ctx.integrations.llm.structured(
                        system=(
                            "You are an SEO strategist. Given a site's Search Console queries with positions and the "
                            "pages that rank, label search intent and propose new terms the site could realistically rank "
                            "for. Prefer terms adjacent to what already ranks. Never invent volumes."
                        ),
                        prompt=json.dumps(
                            {
                                "site": site.url,
                                "queries": [{"q": x.query, "pos": x.position, "imp": x.impressions, "page": path_of(x.best_page)} for x in stats[:60]],
                            }
                        ),
                        schema=Suggestions,
                        effort="medium",
                    )
                    for lab in res.intents:
                        k = kw_rows.get(lab.query.lower())
                        if k:
                            k.intent = lab.intent
                    path_to_id = {path: pid for pid, _, path in pages}
                    for t in res.new_terms:
                        term = t.term.lower().strip()
                        if not term or term in kw_rows:
                            continue
                        k = Keyword(site_id=site_id, term=term, source="suggested", target_page_id=path_to_id.get(t.target_path), notes=t.why, opportunity=50)
                        s.add(k)
                        kw_rows[term] = k
                        suggested += 1
                except Exception as err:
                    await ctx.emit("warn", f"LLM suggestions skipped: {err}", session=s)
            await s.commit()

        striking = sum(1 for x in stats if x.bucket == "striking_distance")
        await ctx.emit(
            "info",
            f"Analysed {len(stats)} queries: {striking} in striking distance, {assigned} focus keywords assigned, {suggested} new terms suggested",
            {"top": [{"q": x.query, "pos": x.position, "imp": x.impressions, "opp": x.opportunity} for x in stats[:10]]},
        )
        await ctx.handoff("fix.propose", {"site_id": str(site_id), "crawl_id": payload.get("crawl_id")})
        return {"queries": len(stats), "striking": striking, "focus_assigned": assigned, "suggested": suggested}
