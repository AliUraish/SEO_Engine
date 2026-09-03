from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import Session, SiteDep
from app.api.schemas import KeywordIn, KeywordOut, KeywordPatch, RankingPoint, ScorePoint, TrendPoint
from app.db.base import utcnow
from app.db.models import Crawl, Keyword, Page, Ranking

router = APIRouter(tags=["keywords"])


@router.get("/sites/{site_id}/keywords", response_model=list[KeywordOut])
async def list_keywords(
    site: SiteDep,
    s: Session,
    sort: str = Query("opportunity", pattern=r"^(opportunity|impressions|clicks|position|term)$"),
    bucket: str | None = None,
    tracked: bool | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(200, le=2000),
    offset: int = 0,
) -> list[KeywordOut]:
    since = (utcnow() - timedelta(days=28)).date()
    agg = (
        select(
            Ranking.keyword_id,
            func.sum(Ranking.clicks).label("clicks"),
            func.sum(Ranking.impressions).label("imps"),
            (func.sum(Ranking.position * Ranking.impressions) / func.nullif(func.sum(Ranking.impressions), 0)).label("pos"),
        )
        .where(Ranking.day >= since)
        .group_by(Ranking.keyword_id)
        .subquery()
    )
    stmt = (
        select(Keyword, func.coalesce(agg.c.clicks, 0), func.coalesce(agg.c.imps, 0), agg.c.pos, Page.path)
        .outerjoin(agg, agg.c.keyword_id == Keyword.id)
        .outerjoin(Page, Page.id == Keyword.target_page_id)
        .where(Keyword.site_id == site.id)
    )
    if bucket:
        stmt = stmt.where(Keyword.bucket == bucket)
    if tracked is not None:
        stmt = stmt.where(Keyword.tracked.is_(tracked))
    if source:
        stmt = stmt.where(Keyword.source == source)
    if q:
        stmt = stmt.where(Keyword.term.ilike(f"%{q}%"))
    order_col = {
        "opportunity": Keyword.opportunity.desc(),
        "impressions": func.coalesce(agg.c.imps, 0).desc(),
        "clicks": func.coalesce(agg.c.clicks, 0).desc(),
        "position": agg.c.pos.asc().nulls_last(),
        "term": Keyword.term.asc(),
    }[sort]
    rows = (await s.execute(stmt.order_by(order_col).limit(limit).offset(offset))).all()
    out = []
    for k, clicks, imps, pos, path in rows:
        item = KeywordOut.model_validate(k)
        item.clicks_28d, item.impressions_28d = int(clicks), int(imps)
        item.position_28d = round(float(pos), 1) if pos is not None else None
        item.target_path = path
        out.append(item)
    return out


@router.post("/sites/{site_id}/keywords", response_model=KeywordOut, status_code=201)
async def add_keyword(site: SiteDep, body: KeywordIn, s: Session) -> Keyword:
    term = body.term.strip().lower()
    existing = await s.scalar(select(Keyword).where(Keyword.site_id == site.id, Keyword.term == term))
    if existing:
        existing.tracked = body.tracked
        if body.target_page_id:
            existing.target_page_id = body.target_page_id
        await s.commit()
        return existing
    k = Keyword(site_id=site.id, term=term, source="manual", tracked=body.tracked, target_page_id=body.target_page_id)
    s.add(k)
    await s.commit()
    return k


@router.patch("/keywords/{keyword_id}", response_model=KeywordOut)
async def patch_keyword(keyword_id: uuid.UUID, body: KeywordPatch, s: Session) -> Keyword:
    k = await s.get(Keyword, keyword_id)
    if not k:
        raise HTTPException(404, "Keyword not found")
    for key, v in body.model_dump(exclude_unset=True).items():
        setattr(k, key, v)
    await s.commit()
    return k


@router.get("/keywords/{keyword_id}/history", response_model=list[RankingPoint])
async def keyword_history(keyword_id: uuid.UUID, s: Session, days: int = 90) -> list[Ranking]:
    since = (utcnow() - timedelta(days=days)).date()
    return list((await s.scalars(select(Ranking).where(Ranking.keyword_id == keyword_id, Ranking.day >= since).order_by(Ranking.day))).all())


@router.get("/sites/{site_id}/analytics/trend", response_model=list[TrendPoint])
async def trend(site: SiteDep, s: Session, days: int = 28) -> list[TrendPoint]:
    since = (utcnow() - timedelta(days=days)).date()
    rows = (
        await s.execute(
            select(
                Ranking.day,
                func.sum(Ranking.clicks),
                func.sum(Ranking.impressions),
                func.sum(Ranking.position * Ranking.impressions) / func.nullif(func.sum(Ranking.impressions), 0),
            )
            .where(Ranking.site_id == site.id, Ranking.day >= since)
            .group_by(Ranking.day)
            .order_by(Ranking.day)
        )
    ).all()
    return [TrendPoint(day=d, clicks=int(c), impressions=int(i), position=round(float(p), 1) if p is not None else None) for d, c, i, p in rows]


@router.get("/sites/{site_id}/analytics/score-history", response_model=list[ScorePoint])
async def score_history(site: SiteDep, s: Session, limit: int = 30) -> list[ScorePoint]:
    crawls = (await s.scalars(select(Crawl).where(Crawl.site_id == site.id, Crawl.status == "done").order_by(Crawl.finished_at.desc()).limit(limit))).all()
    out = [
        ScorePoint(crawl_id=c.id, at=c.finished_at or c.created_at, site_score=int(c.stats["site_score"]), pages=c.pages_found)
        for c in crawls
        if c.stats and "site_score" in c.stats
    ]
    return list(reversed(out))
