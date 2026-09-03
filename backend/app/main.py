"""FastAPI app. The worker and scheduler run inside the same process by default
(WORKER_ENABLED=true); run `python -m app.worker` to run them separately."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.base import Integrations
from app.api.routes import changesets, jobs, keywords, migrations, pages, sites
from app.config import get_settings
from app.db.base import Database
from app.integrations.github import create_github
from app.integrations.gsc import create_search_console
from app.integrations.llm import create_llm
from app.integrations.repo import create_local_repo
from app.logging import setup_logging
from app.queue.jobs import JobQueue
from app.queue.scheduler import Scheduler
from app.queue.worker import Worker

log = logging.getLogger("app")


def build_integrations() -> Integrations:
    return Integrations(llm=create_llm(), gsc=create_search_console(), github=create_github(), repo=create_local_repo())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings = get_settings()
    db = Database()
    await db.create_all()
    queue = JobQueue(db)
    app.state.db, app.state.queue = db, queue
    log.info("db ready (%s) · network %s", "postgres" if db.is_postgres else "sqlite", "ON" if settings.network_enabled else "OFF")

    worker = scheduler = None
    if settings.worker_enabled:
        worker = Worker(db, queue, build_integrations())
        scheduler = Scheduler(db, queue)
        await worker.start()
        await scheduler.start()
    try:
        yield
    finally:
        if scheduler:
            await scheduler.stop()
        if worker:
            await worker.stop()
        await db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="RankOS API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (sites.router, pages.router, keywords.router, changesets.router, migrations.router, jobs.router):
        app.include_router(r, prefix="/api")

    @app.get("/health")
    async def health() -> dict[str, object]:
        s = get_settings()
        return {"ok": True, "network_enabled": s.network_enabled, "worker_enabled": s.worker_enabled}

    return app


app = create_app()
