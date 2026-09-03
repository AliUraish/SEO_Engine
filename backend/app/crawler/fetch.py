"""Single-URL fetch with manual redirect following so the chain is recorded."""

from __future__ import annotations

import time
from urllib.parse import urljoin

import httpx

from app.config import assert_network, get_settings
from app.crawler.parse import FetchMeta


class FetchResult:
    __slots__ = ("meta", "body")

    def __init__(self, meta: FetchMeta, body: str) -> None:
        self.meta = meta
        self.body = body


async def fetch_page(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_s: float | None = None,
    max_redirects: int = 5,
) -> FetchResult:
    assert_network(f"fetch {url}")
    settings = get_settings()
    timeout = timeout_s or settings.crawl_timeout_s
    chain: list[str] = []
    current = url

    for _ in range(max_redirects + 1):
        started = time.perf_counter()
        res = await client.get(
            current,
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": settings.crawl_user_agent, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        )
        ttfb_ms = int((time.perf_counter() - started) * 1000)
        location = res.headers.get("location")
        if 300 <= res.status_code < 400 and location:
            chain.append(current)
            current = urljoin(current, location)
            continue
        ctype = res.headers.get("content-type")
        is_text = not ctype or any(k in ctype.lower() for k in ("text/", "xml", "json", "javascript"))
        body = res.text if is_text else ""
        return FetchResult(
            FetchMeta(
                url=url,
                final_url=current,
                status_code=res.status_code,
                content_type=ctype,
                ttfb_ms=ttfb_ms,
                bytes=len(res.content),
                redirect_chain=chain,
            ),
            body,
        )
    return FetchResult(FetchMeta(url=url, final_url=current, status_code=310, redirect_chain=chain), "")


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(http2=False, limits=httpx.Limits(max_connections=16, max_keepalive_connections=8))
