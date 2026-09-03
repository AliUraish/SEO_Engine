"""Google Search Console (service-account auth, raw REST via httpx)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from app.config import assert_network, get_settings

log = logging.getLogger(__name__)

_API = "https://searchconsole.googleapis.com/webmasters/v3"
_INSPECT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


@dataclass
class GscRow:
    query: str
    page: str
    day: str  # YYYY-MM-DD
    clicks: int
    impressions: int
    ctr: float
    position: float


@dataclass
class UrlInspection:
    url: str
    verdict: str
    coverage_state: str
    google_canonical: str | None
    user_canonical: str | None
    last_crawl_time: str | None
    indexing_state: str | None


class SearchConsole(Protocol):
    enabled: bool

    async def query_analytics(self, property: str, start_date: str, end_date: str, row_limit: int = 25000) -> list[GscRow]: ...
    async def inspect_url(self, property: str, url: str) -> UrlInspection: ...


class GoogleSearchConsole:
    enabled = True

    def __init__(self, service_account_info: dict) -> None:
        self._creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=_SCOPES)

    async def _token(self) -> str:
        if not self._creds.valid:
            await asyncio.to_thread(self._creds.refresh, Request())
        return str(self._creds.token)

    async def query_analytics(self, property: str, start_date: str, end_date: str, row_limit: int = 25000) -> list[GscRow]:
        assert_network("query Google Search Console")
        token = await self._token()
        out: list[GscRow] = []
        start_row = 0
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                res = await client.post(
                    f"{_API}/sites/{_enc(property)}/searchAnalytics/query",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "startDate": start_date,
                        "endDate": end_date,
                        "dimensions": ["query", "page", "date"],
                        "rowLimit": row_limit,
                        "startRow": start_row,
                        "dataState": "final",
                    },
                )
                if res.status_code != 200:
                    raise RuntimeError(f"GSC {res.status_code}: {res.text}")
                rows = res.json().get("rows", [])
                for r in rows:
                    q, p, d = r["keys"]
                    out.append(GscRow(q, p, d, int(r["clicks"]), int(r["impressions"]), float(r["ctr"]), float(r["position"])))
                if len(rows) < row_limit:
                    break
                start_row += row_limit
        return out

    async def inspect_url(self, property: str, url: str) -> UrlInspection:
        assert_network("inspect a URL in Google Search Console")
        token = await self._token()
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(_INSPECT, headers={"Authorization": f"Bearer {token}"}, json={"inspectionUrl": url, "siteUrl": property})
        if res.status_code != 200:
            raise RuntimeError(f"GSC inspect {res.status_code}: {res.text}")
        r = (res.json().get("inspectionResult") or {}).get("indexStatusResult") or {}
        return UrlInspection(
            url=url,
            verdict=r.get("verdict", "UNKNOWN"),
            coverage_state=r.get("coverageState", "UNKNOWN"),
            google_canonical=r.get("googleCanonical"),
            user_canonical=r.get("userCanonical"),
            last_crawl_time=r.get("lastCrawlTime"),
            indexing_state=r.get("indexingState"),
        )


def _enc(property: str) -> str:
    return quote(property, safe="")


class NoopSearchConsole:
    enabled = False

    async def query_analytics(self, property: str, start_date: str, end_date: str, row_limit: int = 25000) -> list[GscRow]:
        raise RuntimeError("Search Console is not configured (set GSC_SERVICE_ACCOUNT_JSON and NETWORK_ENABLED=true)")

    async def inspect_url(self, property: str, url: str) -> UrlInspection:
        raise RuntimeError("Search Console is not configured")


def create_search_console() -> SearchConsole:
    s = get_settings()
    raw = s.gsc_service_account_json
    if not raw or not s.network_enabled:
        log.info("gsc: disabled")
        return NoopSearchConsole()
    text = raw if raw.strip().startswith("{") else open(os.path.expanduser(raw), encoding="utf-8").read()
    info = json.loads(text)
    log.info("gsc: enabled (%s)", info.get("client_email"))
    return GoogleSearchConsole(info)
