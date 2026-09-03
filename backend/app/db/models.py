"""SQLAlchemy models. JSON columns hold the crawler snapshots and agent payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TZDateTime, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))  # origin, no trailing slash
    repo: Mapped[str | None] = mapped_column(String(200))  # owner/name
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    gsc_property: Mapped[str | None] = mapped_column(String(300))
    # {"focus_keywords": {path: kw}, "exclude_paths": [...], "rank_drop_threshold": 3}
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    pages: Mapped[list[Page]] = relationship(back_populates="site", cascade="all, delete-orphan")
    crawls: Mapped[list[Crawl]] = relationship(back_populates="site", cascade="all, delete-orphan")


class Crawl(Base):
    __tablename__ = "crawls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    pages_found: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    site: Mapped[Site] = relationship(back_populates="crawls")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("site_id", "url", name="pages_site_url_uq"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    path: Mapped[str] = mapped_column(String(2000))
    last_crawl_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawls.id", ondelete="SET NULL"), index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    meta_description: Mapped[str | None] = mapped_column(Text)
    canonical: Mapped[str | None] = mapped_column(Text)
    h1: Mapped[list[str]] = mapped_column(JSON, default=list)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # PageSnapshot as dict
    score: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    site: Mapped[Site] = relationship(back_populates="pages")
    issues: Mapped[list[Issue]] = relationship(back_populates="page", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (Index("issues_site_status_idx", "site_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    crawl_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawls.id", ondelete="SET NULL"))
    rule_code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(10))  # critical|high|medium|low|info
    message: Mapped[str] = mapped_column(Text)
    fix_hint: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|fixing|fixed|ignored|regressed
    detected_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    page: Mapped[Page | None] = relationship(back_populates="issues")


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("site_id", "term", name="keywords_site_term_uq"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    term: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(12), default="gsc")  # gsc|suggested|manual
    intent: Mapped[str] = mapped_column(String(16), default="unknown")
    target_page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    opportunity: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    bucket: Mapped[str | None] = mapped_column(String(20))  # striking_distance|defend|long_tail|weak
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class Ranking(Base):
    """One row per keyword × page × day from Search Console."""

    __tablename__ = "rankings"
    __table_args__ = (
        UniqueConstraint("keyword_id", "page_url", "day", name="rankings_kw_page_day_uq"),
        Index("rankings_site_day_idx", "site_id", "day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id", ondelete="CASCADE"), index=True)
    page_url: Mapped[str] = mapped_column(String(2000))
    day: Mapped[date] = mapped_column(Date)
    position: Mapped[float] = mapped_column(Float)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)


class ChangeSet(Base):
    """The approval unit shown on the dashboard.

    pending_approval → approved → pr_opened → merged → verified
                     ↘ rejected                     ↘ failed / rolled_back
    """

    __tablename__ = "change_sets"
    __table_args__ = (Index("change_sets_site_status_idx", "site_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    created_by_agent: Mapped[str] = mapped_column(String(30))
    expected_impact: Mapped[int] = mapped_column(Integer, default=0)
    branch: Mapped[str | None] = mapped_column(String(200))
    pr_number: Mapped[int | None] = mapped_column(Integer)
    pr_url: Mapped[str | None] = mapped_column(String(500))
    merge_sha: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    changes: Mapped[list[Change]] = relationship(back_populates="change_set", cascade="all, delete-orphan")


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    change_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("change_sets.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    issue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("issues.id", ondelete="SET NULL"))
    # title|meta_description|h1|content|alt_text|link|canonical|schema|redirect
    kind: Mapped[str] = mapped_column(String(20))
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    generated_by: Mapped[str] = mapped_column(String(10), default="heuristic")  # heuristic|llm|user
    file_path: Mapped[str | None] = mapped_column(String(1000))
    apply_status: Mapped[str] = mapped_column(String(14), default="pending")  # pending|applied|needs_manual|verified|failed
    apply_note: Mapped[str | None] = mapped_column(Text)

    change_set: Mapped[ChangeSet] = relationship(back_populates="changes")


class Job(Base):
    """DB-backed queue. Agents talk to each other by enqueuing jobs."""

    __tablename__ = "jobs"
    __table_args__ = (Index("jobs_status_run_at_idx", "status", "run_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued|running|done|failed|cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)


class AgentEvent(Base):
    """The inter-agent conversation; the dashboard streams this."""

    __tablename__ = "agent_events"
    __table_args__ = (Index("agent_events_site_created_idx", "site_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    agent: Mapped[str] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(10), default="info")  # info|warn|error|handoff
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)


class MigrationPlan(Base):
    __tablename__ = "migration_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    old_url: Mapped[str] = mapped_column(String(500))
    new_url: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued|crawling|ready|failed
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
