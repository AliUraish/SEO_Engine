"""Old site vs new site → URL map, redirects, gaps, risk and a staged migration plan. Pure logic."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.crawler.parse import PageSnapshot
from app.util.urls import safe_path, slug_of

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "at", "by", "from", "is", "are"}


@dataclass
class UrlMapping:
    old_path: str
    new_path: str | None
    confidence: float
    method: str  # exact|slug|title|content|none
    clicks: int


@dataclass
class Gap:
    path: str
    kind: str
    severity: str
    detail: str


@dataclass
class Step:
    phase: str  # prepare|stage|validate|cutover|monitor
    order: int
    title: str
    detail: str
    done: bool = False


@dataclass
class Plan:
    strategy: str
    risk_score: int
    summary: str
    url_map: list[UrlMapping]
    redirects: list[dict[str, Any]]
    gaps: list[Gap]
    steps: list[Step]
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokens(s: str | None) -> set[str]:
    return {t for t in _TOKEN.findall((s or "").lower()) if t not in _STOP and len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _path_key(p: str) -> str:
    p = p.rstrip("/") or "/"
    return re.sub(r"\.(html?|php|aspx?)$", "", p, flags=re.I).lower()


def build_plan(
    old: Iterable[PageSnapshot],
    new: Iterable[PageSnapshot],
    *,
    old_clicks: dict[str, int] | None = None,
    old_origin: str,
    new_origin: str,
) -> Plan:
    old_pages = [s for s in old if s.ok]
    new_pages = [s for s in new if s.ok]
    clicks = old_clicks or {}

    new_by_path = {_path_key(safe_path(s.final_url)): s for s in new_pages}
    new_by_slug: dict[str, list[PageSnapshot]] = {}
    for s in new_pages:
        new_by_slug.setdefault(slug_of(safe_path(s.final_url)).lower(), []).append(s)

    url_map: list[UrlMapping] = []
    gaps: list[Gap] = []
    used: set[str] = set()
    ordered = sorted(old_pages, key=lambda s: -clicks.get(safe_path(s.final_url), 0))

    # Pass 1: structural matches (exact path, same slug) claim their targets first, so a
    # fuzzy match in pass 2 can never steal a page that obviously belongs to another URL.
    resolved: dict[str, tuple[PageSnapshot | None, float, str]] = {}
    for o in ordered:
        opath = safe_path(o.final_url)
        m = _match_structural(opath, new_by_path, new_by_slug, used)
        if m is not None:
            resolved[opath] = m
            used.add(safe_path(m[0].final_url))
    for o in ordered:
        opath = safe_path(o.final_url)
        if opath in resolved:
            continue
        m = _match_fuzzy(o, new_pages, used)
        resolved[opath] = m
        if m[0] is not None:
            used.add(safe_path(m[0].final_url))

    for o in ordered:
        opath = safe_path(o.final_url)
        c = clicks.get(opath, 0)
        match, conf, method = resolved[opath]
        if match is None:
            url_map.append(UrlMapping(opath, None, 0.0, "none", c))
            sev = "critical" if c >= 50 else "high" if c > 0 else "medium"
            gaps.append(Gap(opath, "missing_page", sev, f"No equivalent found on the new site ({c} clicks/90d). Needs a 301 target."))
            continue
        npath = safe_path(match.final_url)
        url_map.append(UrlMapping(opath, npath, round(conf, 2), method, c))
        gaps.extend(_compare(o, match, opath, npath, c))

    redirects = [{"from": m.old_path, "to": m.new_path, "code": 301} for m in url_map if m.new_path and m.new_path != m.old_path]

    total_clicks = sum(clicks.values()) or 0
    covered = sum(m.clicks for m in url_map if m.new_path)
    unmapped = sum(1 for m in url_map if not m.new_path)
    identical = sum(1 for m in url_map if m.new_path == m.old_path)
    risk = _risk(url_map, gaps, total_clicks, covered)
    host_changes = urlsplit(old_origin).hostname != urlsplit(new_origin).hostname
    strategy = "staged_subdomain" if (risk >= 15 or host_changes) else "direct_cutover"

    stats = {
        "old_pages": len(old_pages),
        "new_pages": len(new_pages),
        "mapped": len(url_map) - unmapped,
        "unmapped": unmapped,
        "identical": identical,
        "old_traffic_covered": round(covered / total_clicks, 3) if total_clicks else None,
        "host_changes": host_changes,
    }
    return Plan(
        strategy=strategy,
        risk_score=risk,
        summary=_summary(stats, risk, strategy, gaps),
        url_map=url_map,
        redirects=redirects,
        gaps=sorted(gaps, key=lambda g: ("critical", "high", "medium", "low").index(g.severity)),
        steps=_steps(strategy, old_origin, new_origin, host_changes, len(redirects)),
        stats=stats,
    )


def _match_structural(
    opath: str,
    by_path: dict[str, PageSnapshot],
    by_slug: dict[str, list[PageSnapshot]],
    used: set[str],
) -> tuple[PageSnapshot, float, str] | None:
    exact = by_path.get(_path_key(opath))
    if exact:
        return exact, 1.0, "exact"
    slug = slug_of(opath).lower()
    if slug and slug in by_slug:
        cands = [s for s in by_slug[slug] if safe_path(s.final_url) not in used] or by_slug[slug]
        return cands[0], 0.9, "slug"
    return None


def _match_fuzzy(o: PageSnapshot, new_pages: list[PageSnapshot], used: set[str]) -> tuple[PageSnapshot | None, float, str]:
    ot = _tokens(o.title)
    best, best_sim = None, 0.0
    for n in (p for p in new_pages if safe_path(p.final_url) not in used):  # fuzzy matches never steal a claimed page
        sim = _jaccard(ot, _tokens(n.title))
        if sim > best_sim:
            best, best_sim = n, sim
    if best and best_sim >= 0.6:
        return best, 0.7 * best_sim + 0.2, "title"
    oc = _tokens(" ".join(o.h1) + " " + o.text_sample[:400])
    best, best_sim = None, 0.0
    for n in (p for p in new_pages if safe_path(p.final_url) not in used):
        sim = _jaccard(oc, _tokens(" ".join(n.h1) + " " + n.text_sample[:400]))
        if sim > best_sim:
            best, best_sim = n, sim
    if best and best_sim >= 0.5:
        return best, 0.5 * best_sim + 0.2, "content"
    return None, 0.0, "none"


def _compare(o: PageSnapshot, n: PageSnapshot, opath: str, npath: str, clicks: int) -> list[Gap]:
    out: list[Gap] = []
    hi = "high" if clicks > 0 else "medium"
    if n.meta_robots and "noindex" in n.meta_robots.lower():
        out.append(Gap(npath, "noindex", "critical", "New page is noindex — fine on staging, fatal at cutover."))
    if o.title and n.title and _jaccard(_tokens(o.title), _tokens(n.title)) < 0.5:
        out.append(Gap(npath, "title_changed", hi, f'Title changed from "{o.title}" to "{n.title}"; expect rank volatility.'))
    if o.meta_description and not n.meta_description:
        out.append(Gap(npath, "meta_changed", "medium", "Meta description dropped on the new page."))
    if o.h1 and n.h1 and _jaccard(_tokens(o.h1[0]), _tokens(n.h1[0])) < 0.5:
        out.append(Gap(npath, "h1_changed", "medium", f'H1 changed from "{o.h1[0]}" to "{n.h1[0]}".'))
    if o.word_count >= 200 and n.word_count < o.word_count * 0.7:
        out.append(Gap(npath, "thinner_content", hi, f"Content shrank from {o.word_count} to {n.word_count} words."))
    if n.canonical and safe_path(n.canonical).rstrip("/") != npath.rstrip("/"):
        out.append(Gap(npath, "canonical_mismatch", "high", f"New page canonicalises to {n.canonical}."))
    if o.json_ld_types and not n.json_ld_types:
        out.append(Gap(npath, "lost_schema", "low", f"Structured data {o.json_ld_types} not carried over."))
    return out


def _risk(url_map: list[UrlMapping], gaps: list[Gap], total_clicks: int, covered: int) -> int:
    unmapped_share = (1 - covered / total_clicks) if total_clicks else (sum(1 for m in url_map if not m.new_path) / max(1, len(url_map)))
    crit = sum(1 for g in gaps if g.severity == "critical")
    high = sum(1 for g in gaps if g.severity == "high")
    low_conf = sum(1 for m in url_map if m.new_path and m.confidence < 0.7)
    score = 60 * unmapped_share + 8 * crit + 2 * high + 1.5 * low_conf
    return int(max(0, min(100, round(score))))


def _summary(stats: dict[str, Any], risk: int, strategy: str, gaps: list[Gap]) -> str:
    cov = stats.get("old_traffic_covered")
    cov_txt = f"{cov * 100:.0f}% of old-site clicks land on a mapped page" if cov is not None else "no traffic data yet"
    crit = sum(1 for g in gaps if g.severity == "critical")
    how = "stage the new site on a subdomain, validate in Search Console, then cut over" if strategy == "staged_subdomain" else "a direct cutover is acceptable"
    return (
        f"{stats['mapped']} of {stats['old_pages']} old pages map to the new site ({stats['unmapped']} unmapped); {cov_txt}. "
        f"Risk {risk}/100 with {crit} critical gaps — {how}."
    )


def _steps(strategy: str, old_origin: str, new_origin: str, host_changes: bool, redirect_count: int) -> list[Step]:
    stage_host = urlsplit(new_origin).hostname or "new.example.com"
    s: list[Step] = [
        Step(
            "prepare",
            1,
            "Freeze a baseline",
            f"Export 90 days of Search Console data for {old_origin} and snapshot all rankings; RankOS keeps this as the comparison point.",
        ),
        Step("prepare", 2, "Inventory old URLs", "Crawl + sitemap + GSC pages = the complete list every old URL must redirect from. Nothing may 404."),
        Step("prepare", 3, "Approve the URL map", f"Review the {redirect_count} proposed 301s and resolve every 'missing_page' gap with a target."),
    ]
    if strategy == "staged_subdomain":
        s += [
            Step(
                "stage",
                4,
                "Deploy the new site to a staging subdomain",
                f'Serve it at {stage_host} with <meta name="robots" content="noindex"> and robots.txt Disallow so Google does not index it early.',
            ),
            Step(
                "stage",
                5,
                "Crawl staging with RankOS",
                "Fix every gap in this plan on staging: titles, H1s, meta, content parity, canonicals, structured data.",
            ),
            Step(
                "validate",
                6,
                "Test the redirect map on staging",
                "Load each old path against the staging host and confirm a single-hop 301 to the mapped page (no chains, no 302s).",
            ),
            Step(
                "validate",
                7,
                "Validate rendering in Search Console",
                "Add the staging property, run URL Inspection (live test) on the top 20 pages, confirm Google renders the content and canonicals.",
            ),
            Step("validate", 8, "Performance parity", "Compare TTFB / page weight on staging vs old; do not cut over slower."),
        ]
        n = 9
    else:
        n = 4
    s += [
        Step(
            "cutover",
            n,
            "Cut over in a low-traffic window",
            "Remove noindex, deploy 301 map, publish the new sitemap.xml, keep the old sitemap live for 30 days listing old URLs so Google recrawls the redirects.",
        ),
        Step(
            "cutover",
            n + 1,
            "Tell Search Console",
            "Submit the new sitemap; " + ("use Change of Address (domain changed)." if host_changes else "request indexing on the top pages."),
        ),
        Step(
            "monitor",
            n + 2,
            "Daily verification for 4 weeks",
            "RankOS re-crawls, checks every 301, and diffs rankings against the baseline; alerts on drops over the threshold.",
        ),
        Step("monitor", n + 3, "Keep redirects for at least a year", "Do not remove the 301 map; update inbound links you control."),
    ]
    return s
