"""Yoast-style page rules. Each check returns None when the page passes."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.audit.types import Finding, PageRule, PageRuleContext
from app.crawler.parse import flesch_reading_ease

_NON_WORD = re.compile(r"[^\w\s]", re.U)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _NON_WORD.sub(" ", s.lower())).strip()


def contains_keyword(text: str | None, keyword: str) -> bool:
    """True if every word of the keyword appears in the text (order-insensitive)."""
    if not text:
        return False
    t = _norm(text)
    words = [w for w in _norm(keyword).split(" ") if w]
    return bool(words) and all(w in t for w in words)


def keyword_density(text: str, keyword: str) -> float:
    t, k = _norm(text), _norm(keyword)
    if not t or not k:
        return 0.0
    words = len(t.split(" "))
    occurrences = t.count(k)
    return (occurrences * len(k.split(" ")) * 100.0) / words if words else 0.0


def _strip_slash(u: str) -> str:
    return re.sub(r"^https?://www\.", "https://", u.rstrip("/"))


def _path(u: str) -> str:
    try:
        return urlsplit(u).path
    except ValueError:
        return u


# ---------- technical ----------
def http_error(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    if 200 <= s.status_code < 400:
        return None
    sev = "critical" if (s.status_code >= 500 or s.status_code == 0) else "high"
    hint = (
        "Restore the page or 301-redirect it to the closest replacement"
        if s.status_code == 404
        else "Fix the server error; Google drops pages that keep failing"
    )
    return Finding("HTTP_ERROR", sev, f"Returned HTTP {s.status_code or 'network error'}", hint, {"status_code": s.status_code})


def not_https(c: PageRuleContext) -> Finding | None:
    if c.snapshot.https:
        return None
    return Finding("NOT_HTTPS", "critical", "Page is not served over HTTPS", "Redirect all HTTP traffic to HTTPS")


def redirect_chain(c: PageRuleContext) -> Finding | None:
    chain = c.snapshot.redirect_chain
    if len(chain) <= 1:
        return None
    return Finding(
        "REDIRECT_CHAIN",
        "medium",
        f"{len(chain)} redirects before reaching the page",
        "Point every link and redirect straight at the final URL",
        {"chain": chain},
    )


def noindex(c: PageRuleContext) -> Finding | None:
    r = c.snapshot.meta_robots
    if not r or "noindex" not in r.lower():
        return None
    return Finding("NOINDEX", "high", f'robots meta is "{r}"', "Remove noindex if this page should rank", {"meta_robots": r})


def canonical_missing(c: PageRuleContext) -> Finding | None:
    if c.snapshot.canonical:
        return None
    return Finding(
        "CANONICAL_MISSING",
        "low",
        'No <link rel="canonical">',
        "Add a self-referencing canonical to prevent duplicate-content dilution",
    )


def canonical_mismatch(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    if not s.canonical or _strip_slash(s.canonical) == _strip_slash(s.final_url):
        return None
    return Finding(
        "CANONICAL_MISMATCH",
        "info",
        f"Canonical is {s.canonical}",
        "Confirm this is intentional; this page will not rank on its own",
        {"canonical": s.canonical},
    )


def viewport_missing(c: PageRuleContext) -> Finding | None:
    if c.snapshot.viewport:
        return None
    return Finding(
        "VIEWPORT_MISSING",
        "high",
        "No viewport meta tag; mobile-first indexing will penalise this",
        'Add <meta name="viewport" content="width=device-width, initial-scale=1">',
    )


def lang_missing(c: PageRuleContext) -> Finding | None:
    if c.snapshot.lang:
        return None
    return Finding("LANG_MISSING", "low", "<html> has no lang attribute", 'Add lang="en" (or the page language) to <html>')


def slow_ttfb(c: PageRuleContext) -> Finding | None:
    ms = c.snapshot.ttfb_ms
    if ms <= 800:
        return None
    return Finding(
        "SLOW_TTFB",
        "high" if ms > 2000 else "medium",
        f"Time to first byte was {ms} ms",
        "Cache the page at the edge or speed up the origin; aim for < 500 ms",
        {"ttfb_ms": ms},
    )


def page_too_heavy(c: PageRuleContext) -> Finding | None:
    b = c.snapshot.bytes
    if b <= 1_500_000:
        return None
    return Finding("PAGE_TOO_HEAVY", "low", f"HTML is {b // 1024} KB", "Move inline scripts/styles out; paginate long lists", {"bytes": b})


def url_unfriendly(c: PageRuleContext) -> Finding | None:
    p = _path(c.snapshot.final_url)
    problems = []
    if len(p) > 100:
        problems.append("longer than 100 chars")
    if re.search(r"[A-Z]", p):
        problems.append("contains uppercase")
    if "_" in p:
        problems.append("uses underscores")
    if not problems:
        return None
    return Finding(
        "URL_UNFRIENDLY",
        "info",
        f"URL path {', '.join(problems)}",
        "Prefer short, lowercase, hyphenated slugs (with 301s from the old path)",
        {"path": p},
    )


# ---------- title ----------
def title_missing(c: PageRuleContext) -> Finding | None:
    if c.snapshot.title:
        return None
    return Finding("TITLE_MISSING", "critical", "Page has no <title>", "Write a 50-60 character title with the focus keyword near the front")


def title_length(c: PageRuleContext) -> Finding | None:
    t = c.snapshot.title
    if not t:
        return None
    n = len(t)
    if n < 30:
        return Finding("TITLE_LENGTH", "medium", f"Title is {n} chars (too short)", "Expand to 50-60 chars; include the keyword and a benefit", {"length": n})
    if n > 60:
        return Finding(
            "TITLE_LENGTH",
            "medium",
            f"Title is {n} chars (will be truncated in results)",
            "Trim to ≤ 60 chars; keep the keyword in the first half",
            {"length": n},
        )
    return None


def title_no_keyword(c: PageRuleContext) -> Finding | None:
    kw, t = c.focus_keyword, c.snapshot.title
    if not kw or not t or contains_keyword(t, kw):
        return None
    return Finding(
        "TITLE_NO_KEYWORD", "high", f'Title does not contain "{kw}"', "Put the focus keyword in the title, ideally at the start", {"focus_keyword": kw}
    )


# ---------- meta description ----------
def meta_desc_missing(c: PageRuleContext) -> Finding | None:
    if c.snapshot.meta_description:
        return None
    return Finding(
        "META_DESC_MISSING", "high", "No meta description; Google will invent one", "Write 120-155 chars that promise what the page delivers, with the keyword"
    )


def meta_desc_length(c: PageRuleContext) -> Finding | None:
    d = c.snapshot.meta_description
    if not d:
        return None
    n = len(d)
    if n < 70:
        return Finding("META_DESC_LENGTH", "low", f"Meta description is {n} chars (short)", "Use 120-155 chars", {"length": n})
    if n > 160:
        return Finding("META_DESC_LENGTH", "low", f"Meta description is {n} chars (will be cut)", "Trim to ≤ 155 chars", {"length": n})
    return None


def meta_desc_no_keyword(c: PageRuleContext) -> Finding | None:
    kw, d = c.focus_keyword, c.snapshot.meta_description
    if not kw or not d or contains_keyword(d, kw):
        return None
    return Finding("META_DESC_NO_KEYWORD", "medium", f'Meta description lacks "{kw}"', "Mention the keyword once, naturally", {"focus_keyword": kw})


# ---------- headings ----------
def h1_missing(c: PageRuleContext) -> Finding | None:
    if c.snapshot.h1:
        return None
    return Finding("H1_MISSING", "high", "Page has no H1", "Add one H1 that states the page topic")


def h1_multiple(c: PageRuleContext) -> Finding | None:
    h = c.snapshot.h1
    if len(h) <= 1:
        return None
    return Finding("H1_MULTIPLE", "medium", f"{len(h)} H1 tags found", "Keep a single H1; demote the rest to H2", {"h1": h})


def h1_no_keyword(c: PageRuleContext) -> Finding | None:
    kw, h = c.focus_keyword, c.snapshot.h1
    if not kw or not h or any(contains_keyword(x, kw) for x in h):
        return None
    return Finding("H1_NO_KEYWORD", "medium", f'H1 lacks "{kw}"', "Work the keyword into the H1", {"focus_keyword": kw, "h1": h})


def no_subheadings(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    if s.word_count <= 300 or s.h2 or s.h3:
        return None
    return Finding("NO_SUBHEADINGS", "low", f"{s.word_count} words with no H2/H3", "Add an H2 every 200-300 words")


# ---------- content ----------
def thin_content(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    if not s.ok or s.word_count >= 300:
        return None
    return Finding(
        "THIN_CONTENT",
        "high" if s.word_count < 100 else "medium",
        f"Only {s.word_count} words of visible text",
        "Aim for 300+ words that fully answer the search intent",
        {"word_count": s.word_count},
    )


def keyword_not_in_intro(c: PageRuleContext) -> Finding | None:
    kw, s = c.focus_keyword, c.snapshot
    if not kw or s.word_count <= 50 or contains_keyword(s.text_sample[:600], kw):
        return None
    return Finding(
        "KEYWORD_NOT_IN_INTRO", "medium", f'"{kw}" does not appear in the opening text', "Use the keyword in the first 100 words", {"focus_keyword": kw}
    )


def keyword_density_rule(c: PageRuleContext) -> Finding | None:
    kw, s = c.focus_keyword, c.snapshot
    if not kw or s.word_count < 100:
        return None
    d = keyword_density(s.text_sample, kw)
    if d == 0:
        return Finding(
            "KEYWORD_DENSITY",
            "medium",
            f'"{kw}" never appears in the sampled body text',
            "Use the keyword 2-4 times per 500 words",
            {"density": 0, "focus_keyword": kw},
        )
    if d > 3.5:
        return Finding(
            "KEYWORD_DENSITY",
            "medium",
            f"Keyword density is {d:.1f}% (stuffing risk)",
            "Replace some repeats with synonyms",
            {"density": round(d, 2), "focus_keyword": kw},
        )
    return None


def readability_low(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    score = flesch_reading_ease(s.word_count, s.sentences, s.syllables)
    if score is None or score >= 50:
        return None
    return Finding(
        "READABILITY_LOW", "low", f"Flesch reading ease is {score} (difficult)", "Shorten sentences and swap long words; aim for 60+", {"flesch": score}
    )


# ---------- images ----------
def img_alt_missing(c: PageRuleContext) -> Finding | None:
    imgs = c.snapshot.images
    missing = [i.src for i in imgs if not i.alt]
    if not missing:
        return None
    return Finding(
        "IMG_ALT_MISSING",
        "medium",
        f"{len(missing)} of {len(imgs)} images have no alt text",
        "Describe each image; include the keyword where it fits naturally",
        {"missing": missing[:20]},
    )


# ---------- links ----------
def no_internal_links(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    if not s.ok or any(link.internal for link in s.links):
        return None
    return Finding("NO_INTERNAL_LINKS", "medium", "Page links to no other page on the site", "Link to 2-5 related pages with descriptive anchor text")


_GENERIC = re.compile(r"^(click here|here|read more|more|link|this)$", re.I)


def generic_anchors(c: PageRuleContext) -> Finding | None:
    generic = [link.href for link in c.snapshot.links if link.internal and _GENERIC.match(link.text)]
    if not generic:
        return None
    return Finding(
        "GENERIC_ANCHORS",
        "low",
        f"{len(generic)} internal links use generic anchor text",
        "Use anchor text that names the target page's topic",
        {"anchors": generic[:10]},
    )


# ---------- social / structured data ----------
def og_missing(c: PageRuleContext) -> Finding | None:
    og = c.snapshot.open_graph
    missing = [k for k in ("title", "description", "image") if not og.get(k)]
    if not missing:
        return None
    return Finding(
        "OG_MISSING", "low", "Missing og:" + ", og:".join(missing), "Add Open Graph tags so shares render with a title, blurb and image", {"missing": missing}
    )


def schema_missing(c: PageRuleContext) -> Finding | None:
    s = c.snapshot
    if not s.ok or s.json_ld_types:
        return None
    return Finding("SCHEMA_MISSING", "low", "No JSON-LD structured data", "Add Organization/WebSite on the home page and Article/Product/FAQ where relevant")


PAGE_RULES: list[PageRule] = [
    PageRule("HTTP_ERROR", "Page returns an error status", "technical", "critical", http_error),
    PageRule("NOT_HTTPS", "Page served over HTTP", "technical", "critical", not_https),
    PageRule("REDIRECT_CHAIN", "Redirect chain before final URL", "technical", "medium", redirect_chain),
    PageRule("NOINDEX", "Page blocked from indexing", "technical", "high", noindex),
    PageRule("CANONICAL_MISSING", "No canonical URL", "technical", "low", canonical_missing),
    PageRule("CANONICAL_MISMATCH", "Canonical points elsewhere", "technical", "info", canonical_mismatch),
    PageRule("VIEWPORT_MISSING", "No mobile viewport", "technical", "high", viewport_missing),
    PageRule("LANG_MISSING", "No html lang attribute", "technical", "low", lang_missing),
    PageRule("SLOW_TTFB", "Slow server response", "technical", "medium", slow_ttfb),
    PageRule("PAGE_TOO_HEAVY", "HTML document is very large", "technical", "low", page_too_heavy),
    PageRule("URL_UNFRIENDLY", "URL is long or has uppercase/underscores", "technical", "info", url_unfriendly),
    PageRule("TITLE_MISSING", "Missing title tag", "title", "critical", title_missing),
    PageRule("TITLE_LENGTH", "Title length outside 30-60 chars", "title", "medium", title_length),
    PageRule("TITLE_NO_KEYWORD", "Focus keyword missing from title", "keyword", "high", title_no_keyword),
    PageRule("META_DESC_MISSING", "Missing meta description", "meta", "high", meta_desc_missing),
    PageRule("META_DESC_LENGTH", "Meta description length outside 70-160", "meta", "low", meta_desc_length),
    PageRule("META_DESC_NO_KEYWORD", "Focus keyword missing from meta description", "keyword", "medium", meta_desc_no_keyword),
    PageRule("H1_MISSING", "No H1", "headings", "high", h1_missing),
    PageRule("H1_MULTIPLE", "More than one H1", "headings", "medium", h1_multiple),
    PageRule("H1_NO_KEYWORD", "Focus keyword missing from H1", "keyword", "medium", h1_no_keyword),
    PageRule("NO_SUBHEADINGS", "Long content without subheadings", "headings", "low", no_subheadings),
    PageRule("THIN_CONTENT", "Thin content", "content", "medium", thin_content),
    PageRule("KEYWORD_NOT_IN_INTRO", "Focus keyword not in first paragraph", "keyword", "medium", keyword_not_in_intro),
    PageRule("KEYWORD_DENSITY", "Keyword density out of range", "keyword", "low", keyword_density_rule),
    PageRule("READABILITY_LOW", "Hard to read", "content", "low", readability_low),
    PageRule("IMG_ALT_MISSING", "Images without alt text", "images", "medium", img_alt_missing),
    PageRule("NO_INTERNAL_LINKS", "No internal links out", "links", "medium", no_internal_links),
    PageRule("GENERIC_ANCHORS", "Generic anchor text", "links", "low", generic_anchors),
    PageRule("OG_MISSING", "Open Graph tags missing", "social", "low", og_missing),
    PageRule("SCHEMA_MISSING", "No structured data", "social", "low", schema_missing),
]

# Site-level rules live in audit/site.py; listed here so the catalog is complete.
SITE_RULES_META = [
    {"code": "TITLE_DUPLICATE", "title": "Duplicate title", "category": "title", "severity": "high"},
    {"code": "META_DESC_DUPLICATE", "title": "Duplicate meta description", "category": "meta", "severity": "medium"},
    {"code": "BROKEN_INTERNAL_LINK", "title": "Broken internal link", "category": "links", "severity": "high"},
    {"code": "ORPHAN_PAGE", "title": "Orphan page", "category": "links", "severity": "medium"},
]

_ALWAYS = {"HTTP_ERROR", "REDIRECT_CHAIN", "NOT_HTTPS"}


def run_page_rules(ctx: PageRuleContext) -> list[Finding]:
    """Runs every page rule; on dead pages only the transport rules fire, so a 404 does not spam."""
    out: list[Finding] = []
    dead = ctx.snapshot.dead
    for r in PAGE_RULES:
        if dead and r.code not in _ALWAYS:
            continue
        f = r.check(ctx)
        if f:
            out.append(f)
    return out


def rule_catalog() -> list[dict[str, str]]:
    return [{"code": r.code, "title": r.title, "category": r.category, "severity": r.severity} for r in PAGE_RULES] + SITE_RULES_META
