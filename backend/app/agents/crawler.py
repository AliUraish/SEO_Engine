"""Crawler: fetches the site, stores a snapshot per page, then hands the crawl to the Auditor.
With `urls` it re-crawls only those (used by the Verifier) and does not hand off."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from app.agents.base import AgentContext
from app.crawler.crawl import crawl_site
from app.crawler.parse import PageSnapshot
from app.db.base import utcnow
from app.db.models import Crawl, Page, Site
from app.util.urls import safe_path


class CrawlerAgent:
    name = "crawler"
    handles = ("crawl.site",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        site_id = uuid.UUID(payload["site_id"])
        urls: list[str] | None = payload.get("urls")
        async with ctx.session() as s:
            site = await s.get(Site, site_id)
            if not site:
                raise RuntimeError(f"Site {site_id} not found")
            crawl = await s.get(Crawl, uuid.UUID(payload["crawl_id"])) if payload.get("crawl_id") else None
            if crawl is None:
                crawl = Crawl(site_id=site.id)
                s.add(crawl)
            crawl.status = "running"
            crawl.started_at = utcnow()
            await s.commit()
            crawl_id, origin, settings = crawl.id, site.url, dict(site.settings or {})

        await ctx.emit("info", f"Crawling {origin}", {"crawl_id": str(crawl_id), "reason": payload.get("reason", "scheduled"), "partial": bool(urls)})
        stored = 0

        async def on_page(snap: PageSnapshot) -> None:
            nonlocal stored
            await self._upsert_page(ctx, site_id, crawl_id, snap)
            stored += 1

        async def on_log(msg: str, data: dict[str, Any]) -> None:
            await ctx.emit("info", msg, data)

        try:
            summary = await crawl_site(
                origin,
                on_page=on_page,
                on_log=on_log,
                seeds=urls,
                max_pages=len(urls) if urls else None,
                exclude_paths=settings.get("exclude_paths"),
            )
        except Exception as err:
            async with ctx.session() as s:
                c = await s.get(Crawl, crawl_id)
                if c:
                    c.status, c.finished_at, c.error = "failed", utcnow(), str(err)
                    await s.commit()
            raise

        async with ctx.session() as s:
            c = await s.get(Crawl, crawl_id)
            if c:
                c.status, c.finished_at, c.pages_found, c.stats = "done", utcnow(), stored, summary.as_dict()
                await s.commit()

        await ctx.emit("info", f"Crawl finished: {stored} pages", {"crawl_id": str(crawl_id), **summary.as_dict()})
        if urls is None:
            await ctx.handoff("audit.crawl", {"site_id": str(site_id), "crawl_id": str(crawl_id)})
        return {"crawl_id": str(crawl_id), "pages": stored, **summary.as_dict()}

    async def _upsert_page(self, ctx: AgentContext, site_id: uuid.UUID, crawl_id: uuid.UUID, snap: PageSnapshot) -> None:
        values = {
            "site_id": site_id,
            "url": snap.final_url,
            "path": safe_path(snap.final_url),
            "last_crawl_id": crawl_id,
            "status_code": snap.status_code,
            "title": snap.title,
            "meta_description": snap.meta_description,
            "canonical": snap.canonical,
            "h1": snap.h1,
            "word_count": snap.word_count,
            "snapshot": snap.model_dump(),
            "fetched_at": utcnow(),
        }
        update_cols = {k: v for k, v in values.items() if k not in ("site_id", "url")}
        async with ctx.session() as s:
            if ctx.db.is_postgres:
                stmt = postgresql.insert(Page).values(id=uuid.uuid4(), **values)
                stmt = stmt.on_conflict_do_update(constraint="pages_site_url_uq", set_=update_cols)
                await s.execute(stmt)
            else:
                existing = await s.scalar(select(Page).where(Page.site_id == site_id, Page.url == snap.final_url))
                if existing:
                    for k, v in update_cols.items():
                        setattr(existing, k, v)
                else:
                    stmt = sqlite.insert(Page).values(id=uuid.uuid4(), **values)
                    await s.execute(stmt)
            await s.commit()
