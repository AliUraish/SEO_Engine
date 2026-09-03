"""Fixer: turns the highest-value open issues into a change set (before → after per page element)
and parks it as pending_approval. Nothing is applied or pushed until a human approves on the
dashboard; approval enqueues publish.changeset."""

from __future__ import annotations

import json
import math
import uuid
from collections import Counter
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.agents.base import AgentContext
from app.audit.types import SEVERITY_WEIGHT
from app.changes.generate import FIXABLE, ProposedChange, heuristic_fix
from app.crawler.parse import PageSnapshot
from app.db.base import utcnow
from app.db.models import Change, ChangeSet, Issue, Ranking, Site

ACTIVE_STATUSES = ("pending_approval", "approved", "pr_opened")


class LlmFix(BaseModel):
    issue_id: str
    after: str
    rationale: str


class LlmFixes(BaseModel):
    fixes: list[LlmFix]


class FixerAgent:
    name = "fixer"
    handles = ("fix.propose",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        site_id = uuid.UUID(payload["site_id"])
        max_changes = int(payload.get("max_changes", 15))

        async with ctx.session() as s:
            site = await s.get(Site, site_id)
            if not site:
                raise RuntimeError(f"Site {site_id} not found")

            pending = await s.scalar(select(ChangeSet).where(ChangeSet.site_id == site_id, ChangeSet.status.in_(ACTIVE_STATUSES)).limit(1))
            if pending:
                await ctx.emit(
                    "info", f"Change set {pending.id} is still {pending.status}; not proposing another", {"change_set_id": str(pending.id)}, session=s
                )
                await s.commit()
                return {"skipped": True, "pending_change_set_id": str(pending.id)}

            open_issues = (
                await s.scalars(
                    select(Issue)
                    .options(selectinload(Issue.page))
                    .where(Issue.site_id == site_id, Issue.status == "open", Issue.rule_code.in_(tuple(FIXABLE)))
                    .order_by(Issue.detected_at.desc())
                )
            ).all()
            open_issues = [i for i in open_issues if i.page and i.page.snapshot]
            if not open_issues:
                await ctx.emit("info", "No auto-fixable issues open", session=s)
                await s.commit()
                return {"proposed": 0}

            since = (utcnow() - timedelta(days=28)).date()
            traffic = dict(
                (
                    await s.execute(
                        select(Ranking.page_url, func.sum(Ranking.impressions))
                        .where(Ranking.site_id == site_id, Ranking.day >= since)
                        .group_by(Ranking.page_url)
                    )
                ).all()
            )

            # value = severity × log(traffic): fixes go where the impressions are
            ranked = sorted(
                open_issues,
                key=lambda i: -(SEVERITY_WEIGHT[i.severity] * math.log10((traffic.get(i.page.url, 0) or 0) + 10)),
            )
            seen: set[tuple[uuid.UUID, str]] = set()
            picked: list[Issue] = []
            for i in ranked:
                key = (i.page_id, FIXABLE[i.rule_code])
                if key in seen:
                    continue
                seen.add(key)
                picked.append(i)
                if len(picked) >= max_changes:
                    break

            focus: dict[str, str] = (site.settings or {}).get("focus_keywords", {})
            proposals: list[tuple[Issue, ProposedChange]] = []
            for i in picked:
                snap = PageSnapshot.model_validate(i.page.snapshot)
                change = heuristic_fix(i.rule_code, i.details or {}, snap, focus.get(i.page.path), site.name)
                if change:
                    proposals.append((i, change))

            llm_used = 0
            if ctx.integrations.llm.enabled and proposals:
                try:
                    items = []
                    for i, ch in proposals:
                        snap = PageSnapshot.model_validate(i.page.snapshot)
                        items.append(
                            {
                                "issue_id": str(i.id),
                                "element": ch.kind,
                                "problem": i.message,
                                "focus_keyword": focus.get(i.page.path),
                                "current": ch.before,
                                "draft": ch.after,
                                "page": {"url": snap.final_url, "h1": snap.h1, "intro": snap.text_sample[:500]},
                            }
                        )
                    res = await ctx.integrations.llm.structured(
                        system=(
                            "You are a senior SEO copywriter. For each item write the replacement text for the given element "
                            "(title ≤ 60 chars, meta description 120–155 chars, alt text ≤ 125 chars). Include the focus keyword "
                            "naturally when given. Match the page's tone. Return exactly one fix per issue_id."
                        ),
                        prompt=json.dumps({"site": site.name, "items": items}),
                        schema=LlmFixes,
                        effort="medium",
                    )
                    by_id = {str(i.id): idx for idx, (i, _) in enumerate(proposals)}
                    for f in res.fixes:
                        idx = by_id.get(f.issue_id)
                        if idx is None or not f.after.strip():
                            continue
                        i, ch = proposals[idx]
                        proposals[idx] = (i, ProposedChange(ch.kind, ch.before, f.after.strip(), f.rationale, "llm"))
                        llm_used += 1
                except Exception as err:
                    await ctx.emit("warn", f"LLM rewrite skipped, keeping heuristic drafts: {err}", session=s)

            if not proposals:
                await ctx.emit("info", "Nothing to propose after de-duplication", session=s)
                await s.commit()
                return {"proposed": 0}

            kinds = Counter(ch.kind for _, ch in proposals)
            expected = sum(SEVERITY_WEIGHT[i.severity] for i, _ in proposals)
            cs = ChangeSet(
                site_id=site_id,
                title=f"{len(proposals)} on-page fixes across {len({i.page_id for i, _ in proposals})} pages",
                summary=", ".join(f"{n} {k.replace('_', ' ')}" for k, n in kinds.items()),
                status="pending_approval",
                created_by_agent=self.name,
                expected_impact=expected,
            )
            s.add(cs)
            await s.flush()
            for i, ch in proposals:
                s.add(
                    Change(
                        change_set_id=cs.id,
                        page_id=i.page_id,
                        issue_id=i.id,
                        kind=ch.kind,
                        before=ch.before,
                        after=ch.after,
                        rationale=ch.rationale,
                        generated_by=ch.generated_by,
                    )
                )
                i.status = "fixing"
            await ctx.emit(
                "info",
                f"Proposed change set {cs.id}: {len(proposals)} edits ({llm_used} LLM-written) — awaiting approval on the dashboard",
                {"change_set_id": str(cs.id), "expected_impact": expected},
                session=s,
            )
            await s.commit()
            return {"proposed": len(proposals), "change_set_id": str(cs.id), "llm_used": llm_used}
