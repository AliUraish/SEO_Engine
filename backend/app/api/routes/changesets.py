from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import Queue, Session, SiteDep
from app.api.schemas import ChangeOut, ChangePatch, ChangeSetDetailOut, ChangeSetOut, Decision
from app.db.base import utcnow
from app.db.models import Change, ChangeSet, Issue, Page

router = APIRouter(tags=["change-sets"])


@router.get("/sites/{site_id}/change-sets", response_model=list[ChangeSetOut])
async def list_change_sets(site: SiteDep, s: Session, status: str | None = None, limit: int = Query(50, le=500)) -> list[ChangeSetOut]:
    counts = select(Change.change_set_id, func.count().label("n")).group_by(Change.change_set_id).subquery()
    stmt = select(ChangeSet, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.change_set_id == ChangeSet.id).where(ChangeSet.site_id == site.id)
    if status:
        stmt = stmt.where(ChangeSet.status == status)
    rows = (await s.execute(stmt.order_by(ChangeSet.created_at.desc()).limit(limit))).all()
    out = []
    for cs, n in rows:
        item = ChangeSetOut.model_validate(cs)
        item.change_count = int(n)
        out.append(item)
    return out


async def _load(cs_id: uuid.UUID, s) -> ChangeSet:  # type: ignore[no-untyped-def]
    cs = await s.scalar(select(ChangeSet).options(selectinload(ChangeSet.changes)).where(ChangeSet.id == cs_id))
    if not cs:
        raise HTTPException(404, "Change set not found")
    return cs


async def _detail(cs: ChangeSet, s) -> ChangeSetDetailOut:  # type: ignore[no-untyped-def]
    page_ids = [c.page_id for c in cs.changes if c.page_id]
    paths = dict((await s.execute(select(Page.id, Page.path).where(Page.id.in_(page_ids)))).all()) if page_ids else {}
    out = ChangeSetDetailOut.model_validate(cs)
    out.change_count = len(cs.changes)
    out.changes = []
    for c in cs.changes:
        item = ChangeOut.model_validate(c)
        item.page_path = paths.get(c.page_id) if c.page_id else None
        out.changes.append(item)
    return out


@router.get("/change-sets/{cs_id}", response_model=ChangeSetDetailOut)
async def get_change_set(cs_id: uuid.UUID, s: Session) -> ChangeSetDetailOut:
    return await _detail(await _load(cs_id, s), s)


@router.post("/change-sets/{cs_id}/approve", response_model=ChangeSetDetailOut)
async def approve(cs_id: uuid.UUID, body: Decision, s: Session, q: Queue) -> ChangeSetDetailOut:
    cs = await _load(cs_id, s)
    if cs.status != "pending_approval":
        raise HTTPException(409, f"Change set is {cs.status}")
    cs.status, cs.decided_at, cs.decision_note = "approved", utcnow(), body.note
    await q.enqueue("publish.changeset", {"site_id": str(cs.site_id), "change_set_id": str(cs.id)}, site_id=cs.site_id, session=s)
    await s.commit()
    return await _detail(cs, s)


@router.post("/change-sets/{cs_id}/reject", response_model=ChangeSetDetailOut)
async def reject(cs_id: uuid.UUID, body: Decision, s: Session) -> ChangeSetDetailOut:
    cs = await _load(cs_id, s)
    if cs.status not in ("pending_approval", "approved", "awaiting_manual", "branch_ready"):
        raise HTTPException(409, f"Change set is {cs.status}")
    cs.status, cs.decided_at, cs.decision_note = "rejected", utcnow(), body.note
    for c in cs.changes:
        if c.issue_id:
            issue = await s.get(Issue, c.issue_id)
            if issue and issue.status == "fixing":
                issue.status = "open"
    await s.commit()
    return await _detail(cs, s)


@router.post("/change-sets/{cs_id}/mark-applied", response_model=ChangeSetDetailOut)
async def mark_applied(cs_id: uuid.UUID, body: Decision, s: Session, q: Queue) -> ChangeSetDetailOut:
    """For sets applied by hand (no repo/GitHub) or merged outside RankOS: flips to merged and verifies."""
    cs = await _load(cs_id, s)
    if cs.status not in ("approved", "awaiting_manual", "branch_ready", "pr_opened"):
        raise HTTPException(409, f"Change set is {cs.status}")
    cs.status, cs.decision_note = "merged", body.note or cs.decision_note
    for c in cs.changes:
        if c.apply_status in ("pending", "needs_manual"):
            c.apply_status = "applied"
    await q.enqueue("verify.changeset", {"site_id": str(cs.site_id), "change_set_id": str(cs.id)}, site_id=cs.site_id, session=s)
    await s.commit()
    return await _detail(cs, s)


@router.post("/change-sets/{cs_id}/verify", response_model=ChangeSetDetailOut)
async def reverify(cs_id: uuid.UUID, s: Session, q: Queue) -> ChangeSetDetailOut:
    cs = await _load(cs_id, s)
    if cs.status not in ("merged", "verified", "failed", "pr_opened"):
        raise HTTPException(409, f"Change set is {cs.status}")
    if cs.status in ("verified", "failed"):
        cs.status = "merged"
    await q.enqueue("verify.changeset", {"site_id": str(cs.site_id), "change_set_id": str(cs.id)}, site_id=cs.site_id, session=s)
    await s.commit()
    return await _detail(cs, s)


@router.patch("/changes/{change_id}", response_model=ChangeOut)
async def edit_change(change_id: uuid.UUID, body: ChangePatch, s: Session) -> Change:
    c = await s.get(Change, change_id)
    if not c:
        raise HTTPException(404, "Change not found")
    cs = await s.get(ChangeSet, c.change_set_id)
    if not cs or cs.status != "pending_approval":
        raise HTTPException(409, "Only pending change sets can be edited")
    c.after, c.generated_by = body.after.strip(), "user"
    await s.commit()
    return c


@router.delete("/changes/{change_id}", status_code=204)
async def drop_change(change_id: uuid.UUID, s: Session) -> None:
    c = await s.get(Change, change_id)
    if not c:
        raise HTTPException(404, "Change not found")
    cs = await s.get(ChangeSet, c.change_set_id)
    if not cs or cs.status != "pending_approval":
        raise HTTPException(409, "Only pending change sets can be edited")
    if c.issue_id:
        issue = await s.get(Issue, c.issue_id)
        if issue and issue.status == "fixing":
            issue.status = "open"
    await s.delete(c)
    await s.commit()
