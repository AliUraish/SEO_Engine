"""Verifier: waits for the PR to merge, then re-crawls the affected pages and checks that the
issues each change targeted are actually gone. Marks the change set verified or failed."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.auditor import audit_pages
from app.agents.base import AgentContext
from app.agents.crawler import CrawlerAgent
from app.crawler.crawl import crawl_site
from app.db.base import aware, utcnow
from app.db.models import ChangeSet, Crawl, Issue, Page, Site

POLL = timedelta(hours=6)
GIVE_UP_AFTER = timedelta(days=14)


class VerifierAgent:
    name = "verifier"
    handles = ("verify.changeset",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        cs_id = uuid.UUID(payload["change_set_id"])
        async with ctx.session() as s:
            cs = await s.scalar(select(ChangeSet).options(selectinload(ChangeSet.changes)).where(ChangeSet.id == cs_id))
            if not cs:
                raise RuntimeError(f"Change set {cs_id} not found")
            site = await s.get(Site, cs.site_id)
            assert site

            # 1. wait for the merge
            if cs.status == "pr_opened":
                gh = ctx.integrations.github
                if gh.enabled and site.repo and cs.pr_number:
                    pr = await gh.get_pull_request(site.repo, cs.pr_number)
                    if pr.merged:
                        cs.status, cs.merge_sha = "merged", pr.merge_sha
                    elif pr.state == "closed":
                        cs.status, cs.decision_note = "rejected", "PR closed without merging"
                        for c in cs.changes:
                            if c.issue_id:
                                issue = await s.get(Issue, c.issue_id)
                                if issue and issue.status == "fixing":
                                    issue.status = "open"
                        await ctx.emit("warn", f"PR #{cs.pr_number} was closed without merging; issues re-opened", {"change_set_id": str(cs_id)}, session=s)
                        await s.commit()
                        return {"status": cs.status}
                if cs.status != "merged":
                    if utcnow() - aware(cs.created_at) > GIVE_UP_AFTER:
                        await ctx.emit("warn", "PR still not merged after 14 days; stopping verification polls", {"change_set_id": str(cs_id)}, session=s)
                        await s.commit()
                        return {"status": cs.status, "gave_up": True}
                    await s.commit()
                    await ctx.handoff("verify.changeset", payload, run_at=utcnow() + POLL)
                    return {"status": cs.status, "waiting": True}

            if cs.status in ("branch_ready", "awaiting_manual", "approved"):
                # Nothing merged yet that we can detect; the dashboard's "mark applied" flips it to merged.
                await ctx.emit(
                    "info", f"Change set is {cs.status}; mark it applied on the dashboard to trigger verification", {"change_set_id": str(cs_id)}, session=s
                )
                await s.commit()
                return {"status": cs.status, "waiting": True}

            if cs.status != "merged":
                await s.commit()
                return {"status": cs.status, "skipped": True}

            # 2. re-crawl the affected pages
            page_ids = [c.page_id for c in cs.changes if c.page_id]
            pages = (await s.scalars(select(Page).where(Page.id.in_(page_ids)))).all() if page_ids else []
            urls = sorted({p.url for p in pages})
            crawl = Crawl(site_id=site.id, status="running", started_at=utcnow(), stats={"reason": "verify", "change_set_id": str(cs_id)})
            s.add(crawl)
            await s.commit()
            crawl_id, site_id = crawl.id, site.id

        await ctx.emit("info", f"Verifying change set: re-crawling {len(urls)} pages", {"change_set_id": str(cs_id), "crawl_id": str(crawl_id)})
        crawler = CrawlerAgent()
        stored = 0

        async def on_page(snap):  # type: ignore[no-untyped-def]
            nonlocal stored
            await crawler._upsert_page(ctx, site_id, crawl_id, snap)
            stored += 1

        try:
            summary = await crawl_site(site.url, on_page=on_page, seeds=urls, max_pages=len(urls) or 1)
        except Exception as err:
            async with ctx.session() as s:
                c = await s.get(Crawl, crawl_id)
                if c:
                    c.status, c.finished_at, c.error = "failed", utcnow(), str(err)
                    await s.commit()
            raise

        # 3. audit those pages and reconcile each change against its issue
        async with ctx.session() as s:
            site = await s.get(Site, site_id)
            assert site
            c_row = await s.get(Crawl, crawl_id)
            if c_row:
                c_row.status, c_row.finished_at, c_row.pages_found = "done", utcnow(), stored
                c_row.stats = {**c_row.stats, **summary.as_dict()}
            rows = (await s.scalars(select(Page).where(Page.site_id == site_id, Page.last_crawl_id == crawl_id))).all()
            await audit_pages(s, site, rows, crawl_id, site_wide=False)
            await s.flush()

            cs = await s.scalar(select(ChangeSet).options(selectinload(ChangeSet.changes)).where(ChangeSet.id == cs_id))
            assert cs
            verified = failed = 0
            for ch in cs.changes:
                issue = await s.get(Issue, ch.issue_id) if ch.issue_id else None
                if issue is None:
                    continue
                if issue.status == "fixed":
                    ch.apply_status = "verified"
                    verified += 1
                else:
                    ch.apply_status = "failed"
                    ch.apply_note = f"Live page still reports {issue.rule_code}: {issue.message}"
                    issue.status = "open"
                    failed += 1
            cs.status = "verified" if verified and failed <= verified / 4 else "failed"
            await ctx.emit(
                "info" if cs.status == "verified" else "error",
                f"Verification {cs.status}: {verified} fixes confirmed live, {failed} not",
                {"change_set_id": str(cs_id), "crawl_id": str(crawl_id)},
                session=s,
            )
            await s.commit()
        return {"status": cs.status, "verified": verified, "failed": failed}
