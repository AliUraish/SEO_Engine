"""API request/response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- sites ----------
class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    repo: str | None = Field(default=None, pattern=r"^[\w.-]+/[\w.-]+$")
    default_branch: str = "main"
    gsc_property: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def _origin_only(cls, v: HttpUrl) -> HttpUrl:
        return v


class SitePatch(BaseModel):
    name: str | None = None
    repo: str | None = None
    default_branch: str | None = None
    gsc_property: str | None = None
    settings: dict[str, Any] | None = None


class SiteOut(ORM):
    id: uuid.UUID
    name: str
    url: str
    repo: str | None
    default_branch: str
    gsc_property: str | None
    settings: dict[str, Any]
    created_at: datetime


# ---------- crawls / pages / issues ----------
class CrawlOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    pages_found: int
    stats: dict[str, Any]
    error: str | None
    created_at: datetime


class PageOut(ORM):
    id: uuid.UUID
    url: str
    path: str
    status_code: int | None
    title: str | None
    meta_description: str | None
    canonical: str | None
    h1: list[str]
    word_count: int
    score: int | None
    fetched_at: datetime | None
    open_issues: int = 0


class IssueOut(ORM):
    id: uuid.UUID
    page_id: uuid.UUID | None
    page_path: str | None = None
    rule_code: str
    severity: str
    message: str
    fix_hint: str | None
    details: dict[str, Any]
    status: str
    detected_at: datetime
    resolved_at: datetime | None


class PageDetailOut(PageOut):
    snapshot: dict[str, Any] | None
    issues: list[IssueOut]


class IssuePatch(BaseModel):
    status: str = Field(pattern=r"^(open|ignored)$")


# ---------- keywords / rankings ----------
class KeywordOut(ORM):
    id: uuid.UUID
    term: str
    source: str
    intent: str
    target_page_id: uuid.UUID | None
    target_path: str | None = None
    tracked: bool
    opportunity: int
    bucket: str | None
    notes: str | None
    clicks_28d: int = 0
    impressions_28d: int = 0
    position_28d: float | None = None


class KeywordIn(BaseModel):
    term: str = Field(min_length=1, max_length=500)
    target_page_id: uuid.UUID | None = None
    tracked: bool = True


class KeywordPatch(BaseModel):
    tracked: bool | None = None
    target_page_id: uuid.UUID | None = None
    intent: str | None = None
    notes: str | None = None


class RankingPoint(BaseModel):
    day: date
    page_url: str
    position: float
    clicks: int
    impressions: int
    ctr: float


class TrendPoint(BaseModel):
    day: date
    clicks: int
    impressions: int
    position: float | None


class ScorePoint(BaseModel):
    crawl_id: uuid.UUID
    at: datetime
    site_score: int
    pages: int


class Overview(BaseModel):
    site: SiteOut
    site_score: int | None
    pages: int
    last_crawl: CrawlOut | None
    issues_by_severity: dict[str, int]
    open_issues: int
    pending_change_sets: int
    tracked_keywords: int
    clicks_28d: int
    impressions_28d: int
    recent_drops: list[dict[str, Any]]
    integrations: dict[str, bool]


# ---------- change sets ----------
class ChangeOut(ORM):
    id: uuid.UUID
    page_id: uuid.UUID | None
    page_path: str | None = None
    issue_id: uuid.UUID | None
    kind: str
    before: str | None
    after: str
    rationale: str
    generated_by: str
    file_path: str | None
    apply_status: str
    apply_note: str | None


class ChangeSetOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    title: str
    summary: str
    status: str
    created_by_agent: str
    expected_impact: int
    branch: str | None
    pr_number: int | None
    pr_url: str | None
    merge_sha: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    change_count: int = 0


class ChangeSetDetailOut(ChangeSetOut):
    changes: list[ChangeOut]


class Decision(BaseModel):
    note: str | None = None


class ChangePatch(BaseModel):
    after: str = Field(min_length=1)


# ---------- migrations ----------
class MigrationIn(BaseModel):
    old_url: HttpUrl
    new_url: HttpUrl


class MigrationOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    old_url: str
    new_url: str
    status: str
    plan: dict[str, Any] | None
    error: str | None
    created_at: datetime


class StepPatch(BaseModel):
    done: bool


# ---------- jobs / events ----------
class JobOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID | None
    type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    run_at: datetime
    parent_job_id: uuid.UUID | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class EventOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID | None
    job_id: uuid.UUID | None
    agent: str
    level: str
    message: str
    data: dict[str, Any]
    created_at: datetime


class EnqueueOut(BaseModel):
    job_id: uuid.UUID
    type: str
