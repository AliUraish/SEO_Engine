"""Site-wide rules that need every page at once, plus scoring."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable

from app.audit.types import SEVERITY_WEIGHT, Finding
from app.crawler.parse import PageSnapshot
from app.util.urls import canon, safe_path


def run_site_rules(snapshots: Iterable[PageSnapshot]) -> dict[str, list[Finding]]:
    """Returns findings keyed by final_url."""
    out: dict[str, list[Finding]] = defaultdict(list)
    snaps = list(snapshots)
    ok = [s for s in snaps if s.ok]
    by_url = {canon(s.final_url): s for s in snaps}

    for title, urls in _group(ok, lambda s: s.title).items():
        if len(urls) < 2:
            continue
        for u in urls:
            out[u].append(
                Finding(
                    "TITLE_DUPLICATE",
                    "high",
                    f'Title "{title}" is shared by {len(urls)} pages',
                    "Give each page a unique title",
                    {"title": title, "pages": [x for x in urls if x != u][:10]},
                )
            )
    for desc, urls in _group(ok, lambda s: s.meta_description).items():
        if len(urls) < 2:
            continue
        for u in urls:
            out[u].append(
                Finding(
                    "META_DESC_DUPLICATE",
                    "medium",
                    f"Meta description is shared by {len(urls)} pages",
                    "Write a unique description per page",
                    {"description": desc, "pages": [x for x in urls if x != u][:10]},
                )
            )

    inbound: dict[str, int] = defaultdict(int)
    for s in ok:
        for link in s.links:
            if not link.internal:
                continue
            target = canon(link.href)
            inbound[target] += 1
            t = by_url.get(target)
            if t and t.dead:
                out[s.final_url].append(
                    Finding(
                        "BROKEN_INTERNAL_LINK",
                        "high",
                        f"Links to {link.href} which returns {t.status_code or 'an error'}",
                        "Update or remove the link",
                        {"href": link.href, "status_code": t.status_code},
                    )
                )
    for s in ok:
        if safe_path(s.final_url) in ("/", ""):
            continue
        if not inbound.get(canon(s.final_url)):
            out[s.final_url].append(Finding("ORPHAN_PAGE", "medium", "No other crawled page links here", "Link to this page from a relevant hub or navigation"))
    return dict(out)


def score_page(findings: Iterable[Finding]) -> int:
    penalty = sum(SEVERITY_WEIGHT[f.severity] for f in findings)
    return max(0, 100 - penalty)


def score_site(pages: Iterable[tuple[int, float]]) -> int:
    """Weighted mean of (score, weight); weight = impressions so important pages count more."""
    items = list(pages)
    total = sum(w for _, w in items)
    if not items or total == 0:
        return 0
    return round(sum(s * w for s, w in items) / total)


def _group(items: list[PageSnapshot], key: Callable[[PageSnapshot], str | None]) -> dict[str, list[str]]:
    m: dict[str, list[str]] = defaultdict(list)
    for s in items:
        k = key(s)
        if k:
            m[k].append(s.final_url)
    return m
