import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def normalize_postgres_url(url: str) -> tuple[str, dict]:
    """Accepts the connection string as Neon/Heroku/psql hand it out and returns
    (SQLAlchemy asyncpg URL, connect_args).

    - `postgres://` / `postgresql://` → `postgresql+asyncpg://`
    - `sslmode=require` / `channel_binding=…` are libpq options asyncpg rejects; they become `ssl="require"`
    - Neon's `-pooler` host runs PgBouncer in transaction mode, which cannot hold prepared
      statements, so the statement cache is switched off there.
    """
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    host = parts.hostname or ""
    if sslmode not in (None, "disable") or host.endswith("neon.tech"):
        connect_args["ssl"] = "require"
    if "-pooler" in host:
        connect_args["statement_cache_size"] = 0
    clean = urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), ""))
    return clean, connect_args


class Database:
    """Engine + session factory. SQLite for zero-setup dev, Postgres (e.g. Neon) in prod."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url or get_settings().database_url
        connect_args: dict = {}
        engine_kwargs: dict = {}
        if self.url.startswith("sqlite"):
            path = self.url.split("///", 1)[-1]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        elif self.url.startswith(("postgres://", "postgresql")):
            self.url, connect_args = normalize_postgres_url(self.url)
            # serverless Postgres drops idle connections; recycle and pre-ping so the worker never inherits a dead one
            engine_kwargs.update(pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)
        self.engine: AsyncEngine = create_async_engine(self.url, echo=False, future=True, connect_args=connect_args, **engine_kwargs)
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
