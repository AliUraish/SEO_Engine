"""Pure keyword analytics over Search Console rows. No I/O."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

Bucket = Literal["striking_distance", "defend", "long_tail", "weak"]


@dataclass
class RankRow:
    query: str
    page: str
    position: float
    clicks: int
    impressions: int


@dataclass
class QueryStat:
    query: str
    clicks: int
    impressions: int
    position: float  # impressions-weighted average
    ctr: float
    best_page: str
    opportunity: int  # 0-100
    bucket: Bucket


def opportunity_score(position: float, impressions: int) -> int:
    """Peaks for positions 4-15 with real impressions: a better title/intro/links moves real traffic."""
    if impressions <= 0:
        return 0
    volume = min(1.0, math.log10(impressions + 1) / 4)  # 10k impressions ≈ 1.0
    if position <= 3:
        distance = 0.25
    elif position <= 10:
        distance = 1.0
    elif position <= 20:
        distance = 0.8
    elif position <= 30:
        distance = 0.4
    else:
        distance = 0.15
    return round(100 * volume * distance)


def bucket_of(position: float, impressions: int) -> Bucket:
    if position <= 3 and impressions >= 20:
        return "defend"
    if 3 < position <= 20 and impressions >= 20:
        return "striking_distance"
    if impressions < 20:
        return "long_tail"
    return "weak"


def aggregate_queries(rows: Iterable[RankRow]) -> list[QueryStat]:
    acc: dict[str, dict] = defaultdict(lambda: {"clicks": 0, "imp": 0, "pos_imp": 0.0, "pages": defaultdict(int)})
    for r in rows:
        q = r.query.strip().lower()
        if not q:
            continue
        a = acc[q]
        w = max(1, r.impressions)
        a["clicks"] += r.clicks
        a["imp"] += r.impressions
        a["pos_imp"] += r.position * w
        a["pages"][r.page] += w
    out: list[QueryStat] = []
    for q, a in acc.items():
        weight = sum(a["pages"].values()) or 1
        pos = a["pos_imp"] / weight
        best = max(a["pages"].items(), key=lambda kv: kv[1])[0] if a["pages"] else ""
        out.append(
            QueryStat(
                query=q,
                clicks=a["clicks"],
                impressions=a["imp"],
                position=round(pos, 1),
                ctr=round(a["clicks"] / a["imp"], 3) if a["imp"] else 0.0,
                best_page=best,
                opportunity=opportunity_score(pos, a["imp"]),
                bucket=bucket_of(pos, a["imp"]),
            )
        )
    out.sort(key=lambda s: (-s.opportunity, -s.impressions))
    return out


def choose_focus_keywords(stats: Iterable[QueryStat], existing: dict[str, str], path_of: Callable[[str], str]) -> dict[str, str]:
    """Highest-opportunity query per page becomes its focus keyword; existing choices are kept."""
    out = dict(existing)
    for s in stats:
        if not s.best_page or s.impressions < 10:
            continue
        p = path_of(s.best_page)
        if p in out:
            continue
        out[p] = s.query
    return out


@dataclass
class Delta:
    recent: float
    baseline: float
    delta: float  # positive = got worse


def position_delta(daily: Iterable[tuple[str, float, int]], recent_days: int = 7, baseline_days: int = 21) -> Delta | None:
    """daily = (day, position, impressions). Compares the last N days to the M days before."""
    rows = sorted(daily, key=lambda x: x[0])
    if len(rows) < 4:
        return None
    recent = rows[-recent_days:]
    baseline = rows[-(recent_days + baseline_days) : -recent_days]
    if not baseline:
        return None

    def wavg(xs: list[tuple[str, float, int]]) -> float:
        w = sum(max(1, x[2]) for x in xs)
        return sum(x[1] * max(1, x[2]) for x in xs) / w

    r, b = wavg(recent), wavg(baseline)
    return Delta(round(r, 1), round(b, 1), round(r - b, 1))
