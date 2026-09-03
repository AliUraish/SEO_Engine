"""Deterministic fix drafting. The LLM (when enabled) rewrites these drafts; without it they ship as-is."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.crawler.parse import PageSnapshot

# Issue codes the Fixer can turn into a concrete text edit; everything else stays advice.
FIXABLE: dict[str, str] = {
    "TITLE_MISSING": "title",
    "TITLE_LENGTH": "title",
    "TITLE_NO_KEYWORD": "title",
    "TITLE_DUPLICATE": "title",
    "META_DESC_MISSING": "meta_description",
    "META_DESC_LENGTH": "meta_description",
    "META_DESC_NO_KEYWORD": "meta_description",
    "META_DESC_DUPLICATE": "meta_description",
    "IMG_ALT_MISSING": "alt_text",
}

_REASONS = {
    "TITLE_MISSING": "Page had no title; search results would show a generated one.",
    "TITLE_LENGTH": "Title length moved into the 50–60 char window so it is not truncated.",
    "TITLE_NO_KEYWORD": 'Focus keyword "{kw}" added to the title, the strongest on-page ranking signal.',
    "TITLE_DUPLICATE": "Title was shared with other pages; made unique to stop them competing.",
    "META_DESC_MISSING": "No meta description; a written one lifts click-through rate.",
    "META_DESC_LENGTH": "Meta description resized to the 120–155 char window.",
    "META_DESC_NO_KEYWORD": 'Focus keyword "{kw}" added to the description (bolded in results).',
    "META_DESC_DUPLICATE": "Description was shared with other pages; made page-specific.",
}


@dataclass
class ProposedChange:
    kind: str
    before: str | None
    after: str
    rationale: str
    generated_by: str = "heuristic"


def heuristic_fix(rule_code: str, details: dict[str, Any], snap: PageSnapshot, focus_keyword: str | None, site_name: str) -> ProposedChange | None:
    kind = FIXABLE.get(rule_code)
    if not kind:
        return None
    kw = focus_keyword
    reason = _REASONS.get(rule_code, "Automated SEO improvement.").format(kw=kw)

    if kind == "title":
        base = (snap.h1[0] if snap.h1 else None) or _first_words(snap.intro, 6) or _slug_title(snap.final_url) or site_name
        title = f"{_cap(kw)} – {base}" if kw and not _includes(base, kw) else base
        suffix = f" | {site_name}"
        if len(title) + len(suffix) <= 60:
            title += suffix
        title = clip(title, 60)
        if title == snap.title:
            return None
        return ProposedChange(kind, snap.title, title, reason)

    if kind == "meta_description":
        text = sentence_clip(snap.intro or snap.text_sample, 150)
        if not text:
            text = f"{(snap.h1[0] if snap.h1 else None) or snap.title or site_name}. Learn more on {site_name}."
        if kw and not _includes(text, kw):
            text = sentence_clip(f"{_cap(kw)}: {text}", 155)
        if text == snap.meta_description:
            return None
        return ProposedChange(kind, snap.meta_description, text, reason)

    if kind == "alt_text":
        missing: list[str] = list(details.get("missing") or [])
        if not missing:
            return None
        extra = f" {len(missing) - 1} more need the same treatment." if len(missing) > 1 else ""
        return ProposedChange(kind, missing[0], humanize_filename(missing[0]), f"Image has no alt text; derived from filename.{extra}")
    return None


# ---------- text helpers ----------
def clip(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    cut = s[:max_len]
    at = cut.rfind(" ")
    out = cut[:at] if at > max_len * 0.6 else cut
    return re.sub(r"[\s\-–|,:;]+$", "", out)


def sentence_clip(s: str, max_len: int) -> str:
    t = re.sub(r"\s+", " ", s).strip()
    if len(t) <= max_len:
        return t
    cut = t[:max_len]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end > max_len * 0.5:
        return cut[: end + 1]
    return re.sub(r"[.,;:]$", "", clip(cut, max_len)) + "…"


def humanize_filename(src: str) -> str:
    name = src.split("/")[-1].split("?")[0]
    words = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.I)
    words = re.sub(r"[-_]+", " ", words)
    words = re.sub(r"\b\d{2,}\b", "", words)
    words = re.sub(r"\s+", " ", words).strip()
    return _cap(words) if words else "Image"


def _first_words(s: str, n: int) -> str | None:
    w = s.split()[:n]
    return re.sub(r"[.,;:!?]+$", "", " ".join(w)) if len(w) >= 3 else None


def _slug_title(url: str) -> str | None:
    try:
        slug = urlsplit(url).path.rstrip("/").split("/")[-1]
    except ValueError:
        return None
    slug = re.sub(r"\.(html?|php)$", "", slug, flags=re.I)
    words = [w for w in re.split(r"[-_]+", slug) if w]
    return " ".join(_cap(w) for w in words) if words else None


def _includes(text: str, kw: str) -> bool:
    t = text.lower()
    return all(w in t for w in kw.lower().split())


def _cap(s: str | None) -> str:
    return s[:1].upper() + s[1:] if s else ""
