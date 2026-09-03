from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import Queue, Session, SiteDep
from app.api.schemas import MigrationIn, MigrationOut, StepPatch
from app.db.models import MigrationPlan
from app.util.urls import origin_of

router = APIRouter(tags=["migrations"])


@router.post("/sites/{site_id}/migrations", response_model=MigrationOut, status_code=202)
async def create_migration(site: SiteDep, body: MigrationIn, s: Session, q: Queue) -> MigrationPlan:
    row = MigrationPlan(site_id=site.id, old_url=origin_of(str(body.old_url)), new_url=origin_of(str(body.new_url)))
    s.add(row)
    await s.flush()
    await q.enqueue("migration.plan", {"site_id": str(site.id), "plan_id": str(row.id)}, site_id=site.id, session=s)
    await s.commit()
    return row


@router.get("/sites/{site_id}/migrations", response_model=list[MigrationOut])
async def list_migrations(site: SiteDep, s: Session) -> list[MigrationPlan]:
    return list((await s.scalars(select(MigrationPlan).where(MigrationPlan.site_id == site.id).order_by(MigrationPlan.created_at.desc()))).all())


@router.get("/migrations/{plan_id}", response_model=MigrationOut)
async def get_migration(plan_id: uuid.UUID, s: Session) -> MigrationPlan:
    row = await s.get(MigrationPlan, plan_id)
    if not row:
        raise HTTPException(404, "Migration plan not found")
    return row


@router.post("/migrations/{plan_id}/rerun", response_model=MigrationOut, status_code=202)
async def rerun_migration(plan_id: uuid.UUID, s: Session, q: Queue) -> MigrationPlan:
    row = await s.get(MigrationPlan, plan_id)
    if not row:
        raise HTTPException(404, "Migration plan not found")
    row.status, row.error = "queued", None
    await q.enqueue("migration.plan", {"site_id": str(row.site_id), "plan_id": str(row.id)}, site_id=row.site_id, session=s)
    await s.commit()
    return row


@router.patch("/migrations/{plan_id}/steps/{order}", response_model=MigrationOut)
async def toggle_step(plan_id: uuid.UUID, order: int, body: StepPatch, s: Session) -> MigrationPlan:
    row = await s.get(MigrationPlan, plan_id)
    if not row or not row.plan:
        raise HTTPException(404, "Migration plan not ready")
    plan = dict(row.plan)
    steps = [dict(st) for st in plan.get("steps", [])]
    hit = next((st for st in steps if st.get("order") == order), None)
    if hit is None:
        raise HTTPException(404, "Step not found")
    hit["done"] = body.done
    plan["steps"] = steps
    row.plan = plan
    await s.commit()
    return row
