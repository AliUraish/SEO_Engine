from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import Session, SiteDep
from app.api.schemas import IssueOut, IssuePatch, PageDetailOut, PageOut
from app.audit.rules import rule_catalog
from app.db.base import utcnow
from app.db.models import Issue, Page

router = APIRouter(tags=["pages"])


@router.get("/rules")
async def rules() -> list[dict[str, str]]:
    return rule_catalog()


@router.get("/sites/{site_id}/pages", response_model=list[PageOut])
async def list_pages(
    site: SiteDep,
    s: Session,
    sort: str = Query("score", pattern=r"^(score|path|status_code|word_count|fetched_at)$"),
    order: str = Query("asc", pattern=r"^(asc|desc)$"),
    q: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
) -> list[PageOut]:
    open_count = select(Issue.page_id, func.count().label("n")).where(Issue.status == "open").group_by(Issue.page_id).subquery()
    stmt = select(Page, func.coalesce(open_count.c.n, 0)).outerjoin(open_count, open_count.c.page_id == Page.id).where(Page.site_id == site.id)
    if q:
        stmt = stmt.where(Page.path.ilike(f"%{q}%"))
    col = getattr(Page, sort)
    stmt = stmt.order_by(col.asc().nulls_last() if order == "asc" else col.desc().nulls_last()).limit(limit).offset(offset)
    rows = (await s.execute(stmt)).all()
    out = []
    for p, n in rows:
        item = PageOut.model_validate(p)
        item.open_issues = int(n)
        out.append(item)
    return out


@router.get("/pages/{page_id}", response_model=PageDetailOut)
async def get_page(page_id: uuid.UUID, s: Session) -> PageDetailOut:
    p = await s.scalar(select(Page).options(selectinload(Page.issues)).where(Page.id == page_id))
    if not p:
        raise HTTPException(404, "Page not found")
    out = PageDetailOut.model_validate(p)
    out.open_issues = sum(1 for i in p.issues if i.status == "open")
    out.issues = [IssueOut.model_validate(i) for i in sorted(p.issues, key=lambda i: (i.status != "open", i.detected_at))]
    for i in out.issues:
        i.page_path = p.path
    return out


@router.get("/sites/{site_id}/issues", response_model=list[IssueOut])
async def list_issues(
    site: SiteDep,
    s: Session,
    status: str = "open",
    severity: str | None = None,
    rule_code: str | None = None,
    limit: int = Query(200, le=2000),
    offset: int = 0,
) -> list[IssueOut]:
    stmt = select(Issue, Page.path).outerjoin(Page, Page.id == Issue.page_id).where(Issue.site_id == site.id)
    if status != "all":
        stmt = stmt.where(Issue.status == status)
    if severity:
        stmt = stmt.where(Issue.severity == severity)
    if rule_code:
        stmt = stmt.where(Issue.rule_code == rule_code)
    stmt = stmt.order_by(Issue.detected_at.desc()).limit(limit).offset(offset)
    out = []
    for issue, path in (await s.execute(stmt)).all():
        item = IssueOut.model_validate(issue)
        item.page_path = path
        out.append(item)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    out.sort(key=lambda i: order.get(i.severity, 9))
    return out


@router.patch("/issues/{issue_id}", response_model=IssueOut)
async def patch_issue(issue_id: uuid.UUID, body: IssuePatch, s: Session) -> Issue:
    issue = await s.get(Issue, issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")
    issue.status = body.status
    issue.resolved_at = utcnow() if body.status == "ignored" else None
    await s.commit()
    return issue
