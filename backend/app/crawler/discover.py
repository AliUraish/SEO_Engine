"""robots.txt and sitemap discovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import NetworkDisabledError, get_settings
from app.crawler.fetch import fetch_page


@dataclass
class RobotsInfo:
    is_allowed: Callable[[str], bool]
    sitemaps: list[str] = field(default_factory=list)
    crawl_delay_s: float = 0.0


def _permissive() -> RobotsInfo:
    return RobotsInfo(is_allowed=lambda _u: True)


async def load_robots(client: httpx.AsyncClient, origin: str) -> RobotsInfo:
    """Reads robots.txt; on any failure everything is allowed (as Google does)."""
    ua = get_settings().crawl_user_agent.split("/")[0]
    try:
        res = await fetch_page(client, f"{origin}/robots.txt", timeout_s=8)
        if res.meta.status_code != 200 or not res.body:
            return _permissive()
        rp = RobotFileParser()
        rp.parse(res.body.splitlines())
        delay = rp.crawl_delay(ua)
        sitemaps = rp.site_maps() or []
        return RobotsInfo(is_allowed=lambda u: rp.can_fetch(ua, u), sitemaps=list(sitemaps), crawl_delay_s=float(delay or 0))
    except NetworkDisabledError:
        raise
    except Exception:
        return _permissive()


async def load_sitemaps(client: httpx.AsyncClient, urls: list[str], limit: int) -> list[str]:
    """Recursively reads sitemap.xml / sitemap indexes and returns page URLs."""
    seen: set[str] = set()
    out: list[str] = []
    queue = list(urls)
    while queue and len(out) < limit:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            res = await fetch_page(client, u, timeout_s=10)
        except NetworkDisabledError:
            raise
        except Exception:
            continue
        if res.meta.status_code != 200 or not res.body:
            continue
        soup = BeautifulSoup(res.body, "xml")
        for loc in soup.select("sitemapindex > sitemap > loc"):
            queue.append(loc.get_text(strip=True))
        for loc in soup.select("urlset > url > loc"):
            if len(out) >= limit:
                break
            out.append(loc.get_text(strip=True))
    return out
