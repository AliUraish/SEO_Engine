"""Publisher (runs under the Fixer's name): applies an approved change set to the local repo,
commits on a branch, pushes and opens a PR — each step gated by its integration. Anything it
cannot locate in source is left as a manual task with a note. Then it schedules verification."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.base import AgentContext
from app.db.base import utcnow
from app.db.models import ChangeSet, Page, Site
from app.integrations.repo import ApplyResult

VERIFY_DELAY = timedelta(hours=6)


class PublisherAgent:
    name = "fixer"
    handles = ("publish.changeset",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        cs_id = uuid.UUID(payload["change_set_id"])
        repo, gh = ctx.integrations.repo, ctx.integrations.github

        async with ctx.session() as s:
            cs = await s.scalar(select(ChangeSet).options(selectinload(ChangeSet.changes)).where(ChangeSet.id == cs_id))
            if not cs:
                raise RuntimeError(f"Change set {cs_id} not found")
            if cs.status != "approved":
                await ctx.emit("warn", f"Change set is {cs.status}, not approved; nothing to publish", {"change_set_id": str(cs_id)}, session=s)
                await s.commit()
                return {"skipped": True}
            site = await s.get(Site, cs.site_id)
            assert site
            pages = {p.id: p for p in (await s.scalars(select(Page).where(Page.id.in_([c.page_id for c in cs.changes if c.page_id])))).all()}

            if not repo.enabled:
                for c in cs.changes:
                    c.apply_status, c.apply_note = "needs_manual", "No repo configured (REPO_LOCAL_PATH); apply by hand, then mark applied"
                cs.status = "awaiting_manual"
                await ctx.emit("warn", "Repo not configured — change set needs manual application", {"change_set_id": str(cs_id)}, session=s)
                await s.commit()
                return {"status": cs.status, "applied": 0, "manual": len(cs.changes)}

            branch = f"rankos/seo-{str(cs.id)[:8]}"
            await repo.checkout_branch(branch, site.default_branch)
            applied = manual = 0
            for c in cs.changes:
                page = pages.get(c.page_id) if c.page_id else None
                if c.kind in ("title", "meta_description") and c.before:
                    res = await repo.replace_exact(c.before, c.after, c.file_path)
                elif c.kind == "alt_text":
                    hits = await repo.grep(c.before.split("/")[-1], 3) if c.before else []
                    where = f" in {hits[0]}" if len(hits) == 1 else ""
                    res = ApplyResult("needs_manual", hits[0] if len(hits) == 1 else None, f'Add alt="{c.after}" to the <img> for {c.before}{where}')
                else:
                    res = ApplyResult("needs_manual", None, f"{c.kind} for {page.path if page else '?'}: no source text to replace; set it to: {c.after}")
                c.apply_status, c.file_path, c.apply_note = res.status, res.file_path, res.note
                applied += res.status == "applied"
                manual += res.status != "applied"

            if applied == 0:
                cs.status = "awaiting_manual"
                await ctx.emit(
                    "warn",
                    f"Could not locate any of the {manual} edits in source; all need manual application",
                    {"change_set_id": str(cs_id), "branch": branch},
                    session=s,
                )
                await s.commit()
                return {"status": cs.status, "applied": 0, "manual": manual}

            sha = await repo.commit(f"SEO: {cs.title}\n\n{cs.summary}\n\nProposed by RankOS change set {cs.id}")
            cs.branch = branch
            body = _pr_body(cs, pages)
            if gh.enabled and site.repo:
                await repo.push(branch)
                pr = await gh.open_pull_request(site.repo, site.default_branch, branch, f"SEO: {cs.title}", body)
                cs.status, cs.pr_number, cs.pr_url = "pr_opened", pr.number, pr.url
                await ctx.emit(
                    "info",
                    f"Opened PR #{pr.number} ({applied} applied, {manual} manual)",
                    {"change_set_id": str(cs_id), "pr_url": pr.url, "commit": sha},
                    session=s,
                )
            else:
                cs.status = "branch_ready"
                await ctx.emit(
                    "info",
                    f"Committed {applied} edits to local branch {branch} ({manual} manual); GitHub not configured, push and open the PR yourself",
                    {"change_set_id": str(cs_id), "commit": sha},
                    session=s,
                )
            await s.commit()

        # Verifier polls for the merge and re-crawls afterwards.
        await ctx.handoff("verify.changeset", {"site_id": str(site.id), "change_set_id": str(cs_id)}, run_at=utcnow() + VERIFY_DELAY)
        return {"status": cs.status, "applied": applied, "manual": manual, "branch": branch}


def _pr_body(cs: ChangeSet, pages: dict[uuid.UUID, Page]) -> str:
    lines = [f"{cs.summary}\n", "| Page | Element | Before | After | Status |", "|---|---|---|---|---|"]
    for c in cs.changes:
        p = pages.get(c.page_id) if c.page_id else None
        lines.append(f"| {p.path if p else '?'} | {c.kind} | {(c.before or '')[:60]} | {c.after[:60]} | {c.apply_status} |")
    lines.append(f"\nExpected impact: +{cs.expected_impact} score points. Generated by RankOS; change set `{cs.id}`.")
    return "\n".join(lines)
