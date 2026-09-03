"""Auditor: scores every page of a crawl and keeps the issue list a live diff —
fixed things resolve, regressions re-open. Hands off to the Keyword Scout."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext
from app.audit.rules import SITE_RULES_META, run_page_rules
from app.audit.site import run_site_rules, score_page
from app.audit.types import Finding, PageRuleContext
from app.crawler.parse import PageSnapshot
from app.db.base import utcnow
from app.db.models import Crawl, Issue, Page, Site

SITE_RULE_CODES = {r["code"] for r in SITE_RULES_META}


@dataclass
class AuditStats:
    pages: int = 0
    findings: int = 0
    opened: int = 0
    resolved: int = 0
    site_score: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def audit_pages(s: AsyncSession, site: Site, rows: Sequence[Page], crawl_id: uuid.UUID, *, site_wide: bool = True) -> AuditStats:
    """Scores `rows` and reconciles their issues. Site-wide rules (duplicates, orphans) only make
    sense over a full crawl, so the Verifier passes site_wide=False for partial re-crawls."""
    focus: dict[str, str] = (site.settings or {}).get("focus_keywords", {})
    snaps = {p.id: PageSnapshot.model_validate(p.snapshot) for p in rows if p.snapshot}
    site_findings = run_site_rules(snaps.values()) if site_wide else {}
    stats = AuditStats()
    by_sev: Counter[str] = Counter()
    scores: list[int] = []

    for page in rows:
        snap = snaps.get(page.id)
        if snap is None:
            continue
        findings: list[Finding] = run_page_rules(PageRuleContext(snap, focus.get(page.path))) + site_findings.get(snap.final_url, [])
        page.score = score_page(findings)
        scores.append(page.score)

        open_issues = (await s.scalars(select(Issue).where(Issue.page_id == page.id, Issue.status.in_(("open", "fixing"))))).all()
        by_code = {i.rule_code: i for i in open_issues}
        present: set[str] = set()
        for f in findings:
            stats.findings += 1
            by_sev[f.severity] += 1
            present.add(f.rule_code)
            ex = by_code.get(f.rule_code)
            if ex:
                ex.message, ex.severity, ex.details, ex.crawl_id = f.message, f.severity, f.details, crawl_id
            else:
                s.add(
                    Issue(
                        site_id=site.id,
                        page_id=page.id,
                        crawl_id=crawl_id,
                        rule_code=f.rule_code,
                        severity=f.severity,
                        message=f.message,
                        fix_hint=f.fix_hint,
                        details=f.details,
                    )
                )
                stats.opened += 1
        for i in open_issues:
            # site-wide codes are not re-evaluated on partial audits; leave them as they are
            if i.rule_code not in present and (site_wide or i.rule_code not in SITE_RULE_CODES):
                i.status, i.resolved_at = "fixed", utcnow()
                stats.resolved += 1

    stats.pages = len(scores)
    stats.site_score = round(sum(scores) / len(scores)) if scores else 0
    stats.by_severity = dict(by_sev)
    return stats


class AuditorAgent:
    name = "auditor"
    handles = ("audit.crawl",)

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        site_id = uuid.UUID(payload["site_id"])
        crawl_id = uuid.UUID(payload["crawl_id"])

        async with ctx.session() as s:
            site = await s.get(Site, site_id)
            if not site:
                raise RuntimeError(f"Site {site_id} not found")
            rows = (await s.scalars(select(Page).where(Page.site_id == site_id, Page.last_crawl_id == crawl_id))).all()
            stats = await audit_pages(s, site, rows, crawl_id)
            crawl = await s.get(Crawl, crawl_id)
            if crawl:  # score history is read off the crawl row
                crawl.stats = {**(crawl.stats or {}), "site_score": stats.site_score, "findings": stats.findings, "by_severity": stats.by_severity}
            await s.commit()

        await ctx.emit(
            "info",
            f"Audited {stats.pages} pages: {stats.findings} findings ({stats.opened} new, {stats.resolved} resolved), site score {stats.site_score}",
            {"crawl_id": str(crawl_id), **stats.as_dict()},
        )
        await ctx.handoff("keywords.scout", {"site_id": str(site_id), "crawl_id": str(crawl_id)})
        return stats.as_dict()
