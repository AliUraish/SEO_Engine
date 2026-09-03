"""Agent protocol and the per-job context every agent receives."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.models import AgentEvent, Job
from app.integrations.github import GitHubClient
from app.integrations.gsc import SearchConsole
from app.integrations.llm import LLM
from app.integrations.repo import LocalRepo
from app.queue.jobs import JobQueue


@dataclass
class Integrations:
    llm: LLM
    gsc: SearchConsole
    github: GitHubClient
    repo: LocalRepo


class AgentContext:
    """What an agent gets: DB, queue, integrations, and two ways to talk — emit() to the shared
    log the dashboard shows, handoff() to enqueue the next agent's job."""

    def __init__(self, *, db: Database, queue: JobQueue, integrations: Integrations, job: Job, agent: str) -> None:
        self.db = db
        self.queue = queue
        self.integrations = integrations
        self.job = job
        self.agent = agent
        self.log = logging.getLogger(f"agent.{agent}")

    def session(self) -> Any:
        return self.db.session()

    async def emit(self, level: str, message: str, data: dict[str, Any] | None = None, session: AsyncSession | None = None) -> None:
        self.log.log(logging.WARNING if level == "warn" else logging.ERROR if level == "error" else logging.INFO, "%s %s", message, data or "")
        ev = AgentEvent(site_id=self.job.site_id, job_id=self.job.id, agent=self.agent, level=level, message=message, data=data or {})
        if session is not None:
            session.add(ev)
            await session.flush()
            return
        async with self.db.session() as s:
            s.add(ev)
            await s.commit()

    async def handoff(self, type: str, payload: dict[str, Any], *, run_at: datetime | None = None) -> uuid.UUID:
        job = await self.queue.enqueue(type, payload, site_id=self.job.site_id, parent_job_id=self.job.id, run_at=run_at)
        await self.emit("handoff", f"→ {type}", {"next_job_id": str(job.id), "payload": payload})
        return job.id


class Agent(Protocol):
    name: str
    handles: tuple[str, ...]

    async def run(self, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]: ...
