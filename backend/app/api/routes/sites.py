from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import Queue, Session, SiteDep
from app.api.schemas import CrawlOut, EnqueueOut, Overview, SiteIn, SiteOut, SitePatch
from app.config import get_settings
from app.db.base import utcnow
from app.db.models import AgentEvent, ChangeSet, Crawl, Issue, Keyword, Page, Ranking, Site
from app.util.urls import origin_of

router = APIRouter(tags=["sites"])


@router.post("/sites", response_model=SiteOut, status_code=201)
async def create_site(body: SiteIn, s: Session) -> Site:
    site = Site(
        name=body.name,
        url=origin_of(str(body.url)),
        repo=body.repo,
        default_branch=body.default_branch,
        gsc_property=body.gsc_property,
        settings=body.settings,
    )
    s.add(site)
    await s.commit()
    return site


@router.get("/sites", response_model=list[SiteOut])
async def list_sites(s: Session) -> list[Site]:
    return list((await s.scalars(select(Site).order_by(Site.created_at))).all())


@router.get("/sites/{site_id}", response_model=SiteOut)
async def get_site_route(site: SiteDep) -> Site:
    return site


@router.patch("/sites/{site_id}", response_model=SiteOut)
async def patch_site(site: SiteDep, body: SitePatch, s: Session) -> Site:
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "settings" and v is not None:
            site.settings = {**(site.settings or {}), **v}
        else:
            setattr(site, k, v)
    await s.commit()
    return site


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site: SiteDep, s: Session) -> None:
    await s.delete(site)
    await s.commit()


@router.post("/sites/{site_id}/crawl", response_model=EnqueueOut, status_code=202)
async def trigger_crawl(site: SiteDep, q: Queue, s: Session) -> EnqueueOut:
    active = await s.scalar(select(func.count()).select_from(Crawl).where(Crawl.site_id == site.id, Crawl.status.in_(("queued", "running"))))
    if active:
        raise HTTPException(409, "A crawl is already queued or running")
    job = await q.enqueue("crawl.site", {"site_id": str(site.id), "reason": "manual"}, site_id=site.id)
    return EnqueueOut(job_id=job.id, type=job.type)


@router.post("/sites/{site_id}/rank-sync", response_model=EnqueueOut, status_code=202)
async def trigger_rank_sync(site: SiteDep, q: Queue, days: int | None = None) -> EnqueueOut:
    job = await q.enqueue("rank.sync", {"site_id": str(site.id), "days": days}, site_id=site.id)
    return EnqueueOut(job_id=job.id, type=job.type)


@router.get("/sites/{site_id}/overview", response_model=Overview)
async def overview(site: SiteDep, s: Session) -> Overview:
    pages = await s.scalar(select(func.count()).select_from(Page).where(Page.site_id == site.id)) or 0
    score = await s.scalar(select(func.avg(Page.score)).where(Page.site_id == site.id, Page.score.is_not(None)))
    last_crawl = await s.scalar(select(Crawl).where(Crawl.site_id == site.id).order_by(Crawl.created_at.desc()).limit(1))
    sev_rows = (await s.execute(select(Issue.severity, func.count()).where(Issue.site_id == site.id, Issue.status == "open").group_by(Issue.severity))).all()
    by_sev = {sev: n for sev, n in sev_rows}
    pending = await s.scalar(select(func.count()).select_from(ChangeSet).where(ChangeSet.site_id == site.id, ChangeSet.status == "pending_approval")) or 0
    tracked = await s.scalar(select(func.count()).select_from(Keyword).where(Keyword.site_id == site.id, Keyword.tracked.is_(True))) or 0
    since = (utcnow() - timedelta(days=28)).date()
    clicks, imps = (
        await s.execute(
            select(func.coalesce(func.sum(Ranking.clicks), 0), func.coalesce(func.sum(Ranking.impressions), 0)).where(
                Ranking.site_id == site.id, Ranking.day >= since
            )
        )
    ).one()
    drops = (
        await s.scalars(
            select(AgentEvent)
            .where(
                AgentEvent.site_id == site.id,
                AgentEvent.agent == "ranker",
                AgentEvent.level.in_(("warn", "error")),
                AgentEvent.created_at >= utcnow() - timedelta(days=7),
            )
            .order_by(AgentEvent.created_at.desc())
            .limit(10)
        )
    ).all()
    cfg = get_settings()
    return Overview(
        site=SiteOut.model_validate(site),
        site_score=round(score) if score is not None else None,
        pages=pages,
        last_crawl=CrawlOut.model_validate(last_crawl) if last_crawl else None,
        issues_by_severity=by_sev,
        open_issues=sum(by_sev.values()),
        pending_change_sets=pending,
        tracked_keywords=tracked,
        clicks_28d=int(clicks),
        impressions_28d=int(imps),
        recent_drops=[{"at": e.created_at, "message": e.message, **e.data} for e in drops if "keyword" in e.data],
        integrations={
            "network": cfg.network_enabled,
            "llm": bool(cfg.openai_api_key and cfg.network_enabled),
            "gsc": bool(cfg.gsc_service_account_json and cfg.network_enabled and site.gsc_property),
            "github": bool(cfg.github_token and cfg.network_enabled and site.repo),
            "repo": bool(cfg.repo_local_path),
        },
    )


@router.get("/sites/{site_id}/crawls", response_model=list[CrawlOut])
async def list_crawls(site: SiteDep, s: Session, limit: int = 20) -> list[Crawl]:
    return list((await s.scalars(select(Crawl).where(Crawl.site_id == site.id).order_by(Crawl.created_at.desc()).limit(limit))).all())


@router.get("/crawls/{crawl_id}", response_model=CrawlOut)
async def get_crawl(crawl_id: uuid.UUID, s: Session) -> Crawl:
    c = await s.get(Crawl, crawl_id)
    if not c:
        raise HTTPException(404, "Crawl not found")
    return c
