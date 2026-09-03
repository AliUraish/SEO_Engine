from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.models import Site
from app.queue.jobs import JobQueue


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


async def get_session(db: Annotated[Database, Depends(get_db)]) -> AsyncIterator[AsyncSession]:
    async with db.session() as s:
        yield s


Session = Annotated[AsyncSession, Depends(get_session)]
Queue = Annotated[JobQueue, Depends(get_queue)]


async def get_site(site_id: uuid.UUID, s: Session) -> Site:
    site = await s.get(Site, site_id)
    if not site:
        raise HTTPException(404, "Site not found")
    return site


SiteDep = Annotated[Site, Depends(get_site)]
