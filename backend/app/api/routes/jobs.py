from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agents.registry import describe
from app.api.deps import Queue, Session, SiteDep
from app.api.schemas import EventOut, JobOut
from app.db.base import utcnow
from app.db.models import AgentEvent, Job
from app.queue.jobs import JOB_TYPES

router = APIRouter(tags=["jobs"])


@router.get("/agents")
async def agents() -> list[dict[str, object]]:
    return describe()


@router.get("/sites/{site_id}/jobs", response_model=list[JobOut])
async def list_jobs(site: SiteDep, s: Session, status: str | None = None, limit: int = Query(50, le=500)) -> list[Job]:
    stmt = select(Job).where(Job.site_id == site.id)
    if status:
        stmt = stmt.where(Job.status == status)
    return list((await s.scalars(stmt.order_by(Job.created_at.desc()).limit(limit))).all())


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, s: Session) -> Job:
    job = await s.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: uuid.UUID, s: Session, q: Queue) -> Job:
    if not await q.cancel(job_id):
        raise HTTPException(409, "Only queued jobs can be cancelled")
    job = await s.get(Job, job_id)
    assert job
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: uuid.UUID, s: Session) -> Job:
    job = await s.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(409, f"Job is {job.status}")
    job.status, job.attempts, job.error, job.run_at = "queued", 0, None, utcnow()
    await s.commit()
    return job


@router.post("/sites/{site_id}/jobs", response_model=JobOut, status_code=202)
async def enqueue_job(site: SiteDep, body: dict, q: Queue) -> Job:  # type: ignore[type-arg]
    job_type = body.get("type")
    if job_type not in JOB_TYPES:
        raise HTTPException(422, f"type must be one of {list(JOB_TYPES)}")
    payload = {**(body.get("payload") or {}), "site_id": str(site.id)}
    return await q.enqueue(job_type, payload, site_id=site.id)


@router.get("/sites/{site_id}/events", response_model=list[EventOut])
async def list_events(
    site: SiteDep,
    s: Session,
    after: datetime | None = None,
    agent: str | None = None,
    level: str | None = None,
    limit: int = Query(100, le=1000),
) -> list[AgentEvent]:
    stmt = select(AgentEvent).where(AgentEvent.site_id == site.id)
    if after:
        stmt = stmt.where(AgentEvent.created_at > after)
    if agent:
        stmt = stmt.where(AgentEvent.agent == agent)
    if level:
        stmt = stmt.where(AgentEvent.level == level)
    rows = (await s.scalars(stmt.order_by(AgentEvent.created_at.desc()).limit(limit))).all()
    return list(reversed(rows))


@router.get("/sites/{site_id}/events/stream")
async def stream_events(site: SiteDep, request: Request) -> StreamingResponse:
    """Server-sent events: the dashboard's live agent feed."""
    db = request.app.state.db
    site_id = site.id

    async def gen():  # type: ignore[no-untyped-def]
        last = utcnow()
        yield "event: ready\ndata: {}\n\n"
        while not await request.is_disconnected():
            async with db.session() as s:
                rows = (
                    await s.scalars(select(AgentEvent).where(AgentEvent.site_id == site_id, AgentEvent.created_at > last).order_by(AgentEvent.created_at))
                ).all()
            for ev in rows:
                last = max(last, ev.created_at if ev.created_at.tzinfo else ev.created_at.replace(tzinfo=last.tzinfo))
                yield f"event: agent\ndata: {json.dumps(EventOut.model_validate(ev).model_dump(mode='json'))}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
