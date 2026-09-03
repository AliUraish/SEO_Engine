"""Breadth-first crawl of one origin: robots.txt → sitemaps → link discovery."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.config import NetworkDisabledError, get_settings
from app.crawler.discover import load_robots, load_sitemaps
from app.crawler.fetch import fetch_page, make_client
from app.crawler.parse import FetchMeta, PageSnapshot, parse_html
from app.util.urls import is_internal, origin_of

_SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|css|js|mjs|json|xml|pdf|zip|gz|mp4|mp3|woff2?|ttf|eot)(\?.*)?$", re.I)
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$)", re.I)

OnPage = Callable[[PageSnapshot], Awaitable[None]]
OnLog = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class CrawlSummary:
    fetched: int = 0
    ok: int = 0
    redirects: int = 0
    client_errors: int = 0
    server_errors: int = 0
    avg_ttfb_ms: int = 0
    duration_ms: int = 0
    _ttfb_total: int = field(default=0, repr=False)

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "ok": self.ok,
            "redirects": self.redirects,
            "client_errors": self.client_errors,
            "server_errors": self.server_errors,
            "avg_ttfb_ms": self.avg_ttfb_ms,
            "duration_ms": self.duration_ms,
        }


def normalize_url(u: str) -> str | None:
    try:
        p = urlsplit(u)
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)])
    return urlunsplit((p.scheme, p.netloc, p.path or "/", query, ""))


async def crawl_site(
    origin: str,
    *,
    on_page: OnPage,
    on_log: OnLog | None = None,
    seeds: list[str] | None = None,
    max_pages: int | None = None,
    concurrency: int | None = None,
    exclude_paths: list[str] | None = None,
) -> CrawlSummary:
    settings = get_settings()
    origin = origin_of(origin)
    max_pages = max_pages or settings.crawl_max_pages
    concurrency = max(1, concurrency or settings.crawl_concurrency)
    exclude = exclude_paths or []
    started = time.monotonic()
    summary = CrawlSummary()

    async def log(msg: str, data: dict[str, Any] | None = None) -> None:
        if on_log:
            await on_log(msg, data or {})

    async with make_client() as client:
        robots = await load_robots(client, origin)
        sitemap_urls = robots.sitemaps or [f"{origin}/sitemap.xml"]
        from_sitemap = await load_sitemaps(client, sitemap_urls, max_pages)
        await log("discovery", {"sitemap_urls": len(from_sitemap), "robots_sitemaps": len(robots.sitemaps)})

        queue: asyncio.Queue[str] = asyncio.Queue()
        seen: set[str] = set()

        def push(u: str) -> None:
            n = normalize_url(u)
            if not n or n in seen or not is_internal(n, origin) or _SKIP_EXT.search(n):
                return
            path = urlsplit(n).path
            if any(path.startswith(x) for x in exclude) or not robots.is_allowed(n):
                return
            seen.add(n)
            queue.put_nowait(n)

        for s in seeds or [origin + "/"]:
            push(s)
        for s in from_sitemap:
            push(s)

        lock = asyncio.Lock()
        active = 0

        async def worker() -> None:
            nonlocal active
            while True:
                if summary.fetched >= max_pages:
                    return
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    # wait briefly for other workers to enqueue more; exit when all idle
                    if active == 0:
                        return
                    await asyncio.sleep(0.05)
                    continue
                async with lock:
                    active += 1
                try:
                    try:
                        res = await fetch_page(client, url)
                        meta, body = res.meta, res.body
                    except NetworkDisabledError:
                        raise
                    except Exception as err:  # network failure → status 0
                        await log("fetch failed", {"url": url, "error": str(err)})
                        meta, body = FetchMeta(url=url, final_url=url, status_code=0), ""
                    summary.fetched += 1
                    summary._ttfb_total += meta.ttfb_ms
                    if meta.redirect_chain:
                        summary.redirects += 1
                    if meta.status_code == 0 or meta.status_code >= 500:
                        summary.server_errors += 1
                    elif meta.status_code >= 400:
                        summary.client_errors += 1
                    else:
                        summary.ok += 1
                    is_html = not meta.content_type or "html" in meta.content_type.lower()
                    snap = parse_html(body if is_html else "", meta)
                    await on_page(snap)
                    if seeds is None:  # full crawl: follow links
                        for link in snap.links:
                            if link.internal and not link.nofollow:
                                push(link.href)
                    if robots.crawl_delay_s:
                        await asyncio.sleep(robots.crawl_delay_s)
                finally:
                    async with lock:
                        active -= 1

        await asyncio.gather(*(worker() for _ in range(concurrency)))

    summary.avg_ttfb_ms = summary._ttfb_total // summary.fetched if summary.fetched else 0
    summary.duration_ms = int((time.monotonic() - started) * 1000)
    return summary
