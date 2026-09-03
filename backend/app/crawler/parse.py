"""HTML → PageSnapshot. Pure functions, no I/O, fully unit-testable."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.util.urls import is_internal, origin_of, resolve


class FetchMeta(BaseModel):
    url: str
    final_url: str
    status_code: int
    content_type: str | None = None
    ttfb_ms: int = 0
    bytes: int = 0
    redirect_chain: list[str] = Field(default_factory=list)


class ImageRef(BaseModel):
    src: str
    alt: str | None


class LinkRef(BaseModel):
    href: str
    text: str
    internal: bool
    nofollow: bool


class PageSnapshot(BaseModel):
    """Everything the audit rules need from one document."""

    url: str
    final_url: str
    status_code: int
    content_type: str | None
    ttfb_ms: int
    bytes: int
    title: str | None
    meta_description: str | None
    meta_robots: str | None
    canonical: str | None
    lang: str | None
    viewport: str | None
    h1: list[str]
    h2: list[str]
    h3: list[str]
    text_sample: str  # first ~2000 chars of visible text
    intro: str = ""  # first real paragraph (>= 40 chars); what a meta description should be drawn from
    word_count: int
    paragraphs: int
    sentences: int
    syllables: int
    images: list[ImageRef]
    links: list[LinkRef]
    open_graph: dict[str, str]
    twitter: dict[str, str]
    json_ld_types: list[str]
    hreflang: list[dict[str, str]]
    https: bool
    redirect_chain: list[str]

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def dead(self) -> bool:
        return self.status_code == 0 or self.status_code >= 400


_WS = re.compile(r"\s+")


def normalize_ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


def parse_html(html: str, meta: FetchMeta) -> PageSnapshot:
    soup = BeautifulSoup(html or "", "lxml")
    origin = origin_of(meta.final_url)

    # JSON-LD before scripts are stripped
    json_ld_types: list[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            _collect_types(json.loads(tag.get_text() or ""), json_ld_types)
        except (ValueError, TypeError):
            pass

    head = soup.head
    title = normalize_ws(soup.title.get_text()) if soup.title else ""

    def meta_content(**attrs: str) -> str | None:
        tag = (head or soup).find("meta", attrs=attrs)
        if tag is None:
            return None
        v = tag.get("content")
        return normalize_ws(str(v)) if v else None

    canonical_tag = (head or soup).find("link", rel=lambda r: r and "canonical" in r)
    canonical_href = canonical_tag.get("href") if canonical_tag else None

    hreflang: list[dict[str, str]] = []
    for tag in (head or soup).find_all("link", rel=lambda r: r and "alternate" in r):
        if tag.get("hreflang"):
            hreflang.append({"lang": str(tag["hreflang"]), "href": resolve(str(tag.get("href") or ""), meta.final_url)})

    og: dict[str, str] = {}
    tw: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        prop = str(tag.get("property") or "")
        name = str(tag.get("name") or "")
        content = tag.get("content")
        if not content:
            continue
        if prop.startswith("og:"):
            og[prop[3:]] = normalize_ws(str(content))
        elif name.startswith("twitter:"):
            tw[name[8:]] = normalize_ws(str(content))

    # strip non-content before reading text
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()

    body = soup.body or soup
    text = normalize_ws(body.get_text(" "))
    words = text.split() if text else []
    sentences = max(1, len(re.findall(r"[.!?]+(?:\s|$)", text))) if text else 0
    syllables = sum(count_syllables(w) for w in words)
    para_texts = [normalize_ws(p.get_text(" ")) for p in body.find_all("p")]
    paragraphs = sum(1 for x in para_texts if x)
    intro = next((x for x in para_texts if len(x) >= 40), "")

    images = [
        ImageRef(
            src=resolve(str(img.get("src") or img.get("data-src") or ""), meta.final_url),
            alt=(str(img["alt"]).strip() if img.has_attr("alt") else None),
        )
        for img in body.find_all("img")
    ]

    links: list[LinkRef] = []
    for a in body.find_all("a", href=True):
        href = resolve(str(a["href"]), meta.final_url)
        if not href.lower().startswith(("http://", "https://")):
            continue
        rel = str(a.get("rel") or "")
        if isinstance(a.get("rel"), list):
            rel = " ".join(a.get("rel"))  # type: ignore[arg-type]
        links.append(
            LinkRef(
                href=href,
                text=normalize_ws(a.get_text())[:200],
                internal=is_internal(href, origin),
                nofollow="nofollow" in rel.lower().split(),
            )
        )

    html_tag = soup.find("html")
    lang = str(html_tag.get("lang") or "").strip() if html_tag else ""

    return PageSnapshot(
        url=meta.url,
        final_url=meta.final_url,
        status_code=meta.status_code,
        content_type=meta.content_type,
        ttfb_ms=meta.ttfb_ms,
        bytes=meta.bytes,
        title=title or None,
        meta_description=meta_content(name="description"),
        meta_robots=meta_content(name="robots"),
        canonical=resolve(str(canonical_href), meta.final_url) if canonical_href else None,
        lang=lang or None,
        viewport=meta_content(name="viewport"),
        h1=_headings(body, "h1"),
        h2=_headings(body, "h2"),
        h3=_headings(body, "h3"),
        text_sample=text[:2000],
        intro=intro[:1000],
        word_count=len(words),
        paragraphs=paragraphs,
        sentences=sentences,
        syllables=syllables,
        images=images,
        links=links,
        open_graph=og,
        twitter=tw,
        json_ld_types=json_ld_types,
        hreflang=hreflang,
        https=meta.final_url.startswith("https://"),
        redirect_chain=meta.redirect_chain,
    )


def _headings(root: Any, tag: str) -> list[str]:
    return [t for t in (normalize_ws(h.get_text()) for h in root.find_all(tag)) if t]


def _collect_types(data: Any, out: list[str]) -> None:
    if isinstance(data, list):
        for d in data:
            _collect_types(d, out)
    elif isinstance(data, dict):
        t = data.get("@type")
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, list):
            out.extend(x for x in t if isinstance(x, str))
        if isinstance(data.get("@graph"), list):
            _collect_types(data["@graph"], out)


_SYL_STRIP = re.compile(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$")
_SYL_GROUPS = re.compile(r"[aeiouy]{1,2}")


def count_syllables(word: str) -> int:
    """Rough English syllable count; good enough for Flesch reading ease."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    stripped = _SYL_STRIP.sub("", w)
    stripped = re.sub(r"^y", "", stripped)
    groups = _SYL_GROUPS.findall(stripped)
    return max(1, len(groups))


def flesch_reading_ease(word_count: int, sentences: int, syllables: int) -> int | None:
    """0-100, higher = easier. None when there is too little text to judge."""
    if word_count < 30 or sentences == 0:
        return None
    score = 206.835 - 1.015 * (word_count / sentences) - 84.6 * (syllables / word_count)
    return int(max(0, min(100, round(score))))
