"""DB-backed job queue. Works on SQLite and Postgres; claim is optimistic (UPDATE ... WHERE status='queued')."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database, utcnow
from app.db.models import Job

JobType = Literal[
    "crawl.site",
    "audit.crawl",
    "keywords.scout",
    "fix.propose",
    "publish.changeset",
    "verify.changeset",
    "rank.sync",
    "migration.plan",
]

JOB_TYPES: tuple[str, ...] = JobType.__args__  # type: ignore[attr-defined]


class JobQueue:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def enqueue(
        self,
        type: str,
        payload: dict[str, Any],
        *,
        site_id: uuid.UUID | None = None,
        run_at=None,
        max_attempts: int = 3,
        parent_job_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
    ) -> Job:
        job = Job(
            type=type,
            payload=payload,
            site_id=site_id,
            run_at=run_at or utcnow(),
            max_attempts=max_attempts,
            parent_job_id=parent_job_id,
        )
        if session is not None:
            session.add(job)
            await session.flush()
            return job
        async with self.db.session() as s:
            s.add(job)
            await s.commit()
            return job

    async def claim(self, worker_id: str) -> Job | None:
        """Atomically claim the next runnable job for this worker, or None."""
        now = utcnow()
        async with self.db.session() as s:
            for _ in range(5):  # retry on races between workers
                cand = await s.scalar(select(Job.id).where(Job.status == "queued", Job.run_at <= now).order_by(Job.run_at, Job.created_at).limit(1))
                if cand is None:
                    return None
                res = await s.execute(
                    update(Job)
                    .where(Job.id == cand, Job.status == "queued")
                    .values(status="running", locked_at=now, locked_by=worker_id, attempts=Job.attempts + 1, updated_at=now)
                )
                if res.rowcount == 1:
                    await s.commit()
                    return await s.get(Job, cand)
                await s.rollback()
            return None

    async def complete(self, job_id: uuid.UUID, result: dict[str, Any] | None = None) -> None:
        async with self.db.session() as s:
            await s.execute(update(Job).where(Job.id == job_id).values(status="done", result=result or {}, locked_at=None, locked_by=None, updated_at=utcnow()))
            await s.commit()

    async def fail(self, job: Job, error: str) -> str:
        """Fails the job; re-queues with exponential backoff while attempts remain. Returns 'retry' | 'dead'."""
        will_retry = job.attempts < job.max_attempts
        backoff = min(timedelta(minutes=1) * (2 ** max(0, job.attempts - 1)), timedelta(minutes=30))
        async with self.db.session() as s:
            await s.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(
                    status="queued" if will_retry else "failed",
                    error=error[:4000],
                    locked_at=None,
                    locked_by=None,
                    run_at=(utcnow() + backoff) if will_retry else job.run_at,
                    updated_at=utcnow(),
                )
            )
            await s.commit()
        return "retry" if will_retry else "dead"

    async def cancel(self, job_id: uuid.UUID) -> bool:
        async with self.db.session() as s:
            res = await s.execute(update(Job).where(Job.id == job_id, Job.status == "queued").values(status="cancelled", updated_at=utcnow()))
            await s.commit()
            return res.rowcount == 1

    async def recover_stale(self, older_than: timedelta) -> int:
        """Jobs whose worker died mid-run go back to the queue."""
        cutoff = utcnow() - older_than
        async with self.db.session() as s:
            res = await s.execute(
                update(Job).where(Job.status == "running", Job.locked_at < cutoff).values(status="queued", locked_at=None, locked_by=None, updated_at=utcnow())
            )
            await s.commit()
            return int(res.rowcount or 0)

    async def get(self, job_id: uuid.UUID) -> Job | None:
        async with self.db.session() as s:
            return await s.get(Job, job_id)
