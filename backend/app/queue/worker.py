"""Polling worker: claims jobs, dispatches to the agent that handles them, records the outcome."""

from __future__ import annotations

import asyncio
import logging
import socket
import traceback
import uuid
from datetime import timedelta

from app.agents.base import AgentContext, Integrations
from app.agents.registry import agent_for
from app.config import get_settings
from app.db.base import Database
from app.db.models import AgentEvent
from app.queue.jobs import JobQueue

log = logging.getLogger("worker")
STALE_AFTER = timedelta(minutes=30)


class Worker:
    def __init__(self, db: Database, queue: JobQueue, integrations: Integrations, concurrency: int | None = None) -> None:
        self.db = db
        self.queue = queue
        self.integrations = integrations
        self.concurrency = concurrency or get_settings().worker_concurrency
        self.poll_s = get_settings().worker_poll_s
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._stop.clear()
        recovered = await self.queue.recover_stale(STALE_AFTER)
        if recovered:
            log.warning("recovered %d stale jobs", recovered)
        self._tasks = [asyncio.create_task(self._loop(f"{socket.gethostname()}-{i}")) for i in range(self.concurrency)]
        log.info("worker started (%d slots)", self.concurrency)

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self, worker_id: str) -> None:
        while not self._stop.is_set():
            try:
                job = await self.queue.claim(worker_id)
            except Exception:
                log.exception("claim failed")
                job = None
            if job is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_s)
                except TimeoutError:
                    pass
                continue
            await self.run_job(job)

    async def run_job(self, job) -> None:  # type: ignore[no-untyped-def]
        try:
            agent = agent_for(job.type)
        except RuntimeError as err:
            await self.queue.fail(job, str(err))
            return
        ctx = AgentContext(db=self.db, queue=self.queue, integrations=self.integrations, job=job, agent=agent.name)
        log.info("job %s %s started (attempt %d)", job.type, job.id, job.attempts)
        try:
            result = await agent.run(job.payload or {}, ctx)
            await self.queue.complete(job.id, result)
            log.info("job %s %s done", job.type, job.id)
        except Exception as err:
            outcome = await self.queue.fail(job, f"{type(err).__name__}: {err}\n{traceback.format_exc()[-2000:]}")
            log.exception("job %s %s failed (%s)", job.type, job.id, outcome)
            try:
                async with self.db.session() as s:
                    s.add(
                        AgentEvent(
                            site_id=job.site_id,
                            job_id=job.id,
                            agent=agent.name,
                            level="error",
                            message=f"{type(err).__name__}: {err}"[:1000],
                            data={"outcome": outcome},
                        )
                    )
                    await s.commit()
            except Exception:
                log.exception("could not record failure event")

    async def run_once(self, worker_id: str | None = None) -> bool:
        """Claim and run a single job. Used by tests and the CLI."""
        job = await self.queue.claim(worker_id or f"once-{uuid.uuid4().hex[:6]}")
        if job is None:
            return False
        await self.run_job(job)
        return True
