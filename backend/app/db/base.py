import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, TypeDecorator, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class TZDateTime(TypeDecorator[datetime]):
    """Always-aware UTC datetimes. SQLite drops tzinfo; this puts it back on the way out."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class Database:
    """Engine + session factory. SQLite for zero-setup dev, Postgres in prod."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url or get_settings().database_url
        if self.url.startswith("sqlite"):
            path = self.url.split("///", 1)[-1]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(self.url, echo=False, future=True)
        if self.url.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def _pragmas(dbapi_conn, _):  # type: ignore[no-untyped-def]
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    @property
    def is_postgres(self) -> bool:
        return self.url.startswith("postgresql")

    async def create_all(self) -> None:
        from app.db import models  # noqa: F401  (registers tables)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as s:
            yield s

    async def close(self) -> None:
        await self.engine.dispose()
