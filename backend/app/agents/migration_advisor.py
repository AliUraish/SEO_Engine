"""Migration Advisor: crawls the old and the new site, maps every URL, lists what the new site
loses, and writes the staged plan (subdomain → validate in Search Console → cut over → monitor)."""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select

from app.agents.base import AgentContext
from app.crawler.crawl import crawl_site
from app.crawler.parse import PageSnapshot
from app.db.models import MigrationPlan, Ranking, Site
from app.migration.planner import build_plan
from app.util.urls import canon, safe_path

MAX_PAGES_PER_SIDE = 300


class Narrative(BaseModel):
    executive_summary: str
    top_risks: list[str]
    go_no_go: str


class MigrationAdvisorAgent:
    name = "migration-advisor"
    handles = ("migration.plan",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        plan_id = uuid.UUID(payload["plan_id"])
        async with ctx.session() as s:
            row = await s.get(MigrationPlan, plan_id)
            if not row:
                raise RuntimeError(f"Migration plan {plan_id} not found")
            site = await s.get(Site, row.site_id)
            assert site
            row.status = "crawling"
            await s.commit()
            old_url, new_url, site_id = row.old_url, row.new_url, row.site_id

        try:
            old = await self._crawl(ctx, old_url, "old")
            new = await self._crawl(ctx, new_url, "new")

            async with ctx.session() as s:
                since = date.today() - timedelta(days=90)
                traffic = (
                    await s.execute(
                        select(Ranking.page_url, func.sum(Ranking.clicks)).where(Ranking.site_id == site_id, Ranking.day >= since).group_by(Ranking.page_url)
                    )
                ).all()
            old_origin = canon(old_url)
            clicks = {safe_path(u): int(c or 0) for u, c in traffic if canon(u).startswith(old_origin)}

            plan = build_plan(old, new, old_clicks=clicks, old_origin=old_url, new_origin=new_url).as_dict()

            if ctx.integrations.llm.enabled:
                try:
                    n = await ctx.integrations.llm.structured(
                        system="You are a technical SEO lead reviewing a site migration plan. Be direct about what will lose traffic and what must be fixed before cutover.",
                        prompt=json.dumps(
                            {
                                "stats": plan["stats"],
                                "risk_score": plan["risk_score"],
                                "strategy": plan["strategy"],
                                "gaps": plan["gaps"][:40],
                                "unmapped": [m for m in plan["url_map"] if not m["new_path"]][:30],
                            }
                        ),
                        schema=Narrative,
                        effort="medium",
                    )
                    plan["narrative"] = n.model_dump()
                except Exception as err:
                    await ctx.emit("warn", f"LLM narrative skipped: {err}")

            async with ctx.session() as s:
                row = await s.get(MigrationPlan, plan_id)
                assert row
                row.plan, row.status = plan, "ready"
                await s.commit()
            await ctx.emit("info", f"Migration plan ready: {plan['summary']}", {"plan_id": str(plan_id), **plan["stats"], "risk_score": plan["risk_score"]})
            return {"plan_id": str(plan_id), "risk_score": plan["risk_score"], **plan["stats"]}
        except Exception as err:
            async with ctx.session() as s:
                row = await s.get(MigrationPlan, plan_id)
                if row:
                    row.status, row.error = "failed", str(err)
                    await s.commit()
            raise

    async def _crawl(self, ctx: AgentContext, origin: str, label: str) -> list[PageSnapshot]:
        snaps: list[PageSnapshot] = []

        async def on_page(snap: PageSnapshot) -> None:
            snaps.append(snap)

        summary = await crawl_site(origin, on_page=on_page, max_pages=MAX_PAGES_PER_SIDE)
        await ctx.emit("info", f"Crawled {label} site {origin}: {summary.fetched} pages", summary.as_dict())
        return snaps
