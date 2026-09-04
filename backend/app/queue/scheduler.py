"""Recurring work per site: a full crawl every N hours and a rank sync every day.
Runs as a light tick inside the worker process; enqueues only when nothing equivalent is
queued or running and the last run is older than the interval."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import func, select

from app.db.base import Database, aware, utcnow
from app.db.models import Job, Site
from app.queue.jobs import JobQueue

log = logging.getLogger("scheduler")

DEFAULTS = {"crawl_interval_hours": 24 * 7, "rank_sync_interval_hours": 24}
TICK_S = 300


class Scheduler:
    def __init__(self, db: Database, queue: JobQueue) -> None:
        self.db = db
        self.queue = queue
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=TICK_S)
            except TimeoutError:
                pass

    async def tick(self) -> int:
        enqueued = 0
        async with self.db.session() as s:
            sites = (await s.scalars(select(Site))).all()
            for site in sites:
                cfg = {**DEFAULTS, **(site.settings or {}).get("schedule", {})}
                if not cfg.get("enabled", True):
                    continue
                for job_type, key in (("crawl.site", "crawl_interval_hours"), ("rank.sync", "rank_sync_interval_hours")):
                    hours = float(cfg[key])
                    if hours <= 0:
                        continue
                    active = await s.scalar(
                        select(func.count()).select_from(Job).where(Job.site_id == site.id, Job.type == job_type, Job.status.in_(("queued", "running")))
                    )
                    if active:
                        continue
                    last = await s.scalar(select(func.max(Job.created_at)).where(Job.site_id == site.id, Job.type == job_type))
                    if last is not None and utcnow() - aware(last) < timedelta(hours=hours):
                        continue
                    await self.queue.enqueue(job_type, {"site_id": str(site.id), "reason": "scheduled"}, site_id=site.id, session=s)
                    enqueued += 1
            await s.commit()
        if enqueued:
            log.info("scheduled %d jobs", enqueued)
        return enqueued
