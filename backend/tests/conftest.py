import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("NETWORK_ENABLED", "false")
os.environ.setdefault("WORKER_ENABLED", "false")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.agents.base import Integrations  # noqa: E402
from app.crawler.parse import FetchMeta, PageSnapshot, parse_html  # noqa: E402
from app.db.base import Database  # noqa: E402
from app.integrations.github import NoopGitHub  # noqa: E402
from app.integrations.gsc import NoopSearchConsole  # noqa: E402
from app.integrations.llm import NoopLLM  # noqa: E402
from app.integrations.repo import NoopLocalRepo  # noqa: E402
from app.queue.jobs import JobQueue  # noqa: E402


class MemoryDatabase(Database):
    """One shared in-memory SQLite connection so every session sees the same tables."""

    def __init__(self) -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        self.url = "sqlite+aiosqlite:///:memory:"
        self.engine = create_async_engine(self.url, poolclass=StaticPool, connect_args={"check_same_thread": False})
        from sqlalchemy.ext.asyncio import AsyncSession

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db():
    d = MemoryDatabase()
    await d.create_all()
    yield d
    await d.close()


@pytest.fixture
def queue(db):
    return JobQueue(db)


@pytest.fixture
def integrations():
    return Integrations(llm=NoopLLM(), gsc=NoopSearchConsole(), github=NoopGitHub(), repo=NoopLocalRepo())


@pytest_asyncio.fixture
async def client(db, queue):
    from app.main import create_app

    app = create_app()
    app.router.lifespan_context = _noop_lifespan  # we manage db/queue ourselves
    app.state.db, app.state.queue = db, queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _noop_lifespan(app):
    yield


def snap(url: str, html: str, status: int = 200, ttfb: int = 100, chain: list[str] | None = None) -> PageSnapshot:
    return parse_html(html, FetchMeta(url=url, final_url=url, status_code=status, content_type="text/html", ttfb_ms=ttfb, bytes=len(html), redirect_chain=chain or []))


GOOD_HTML = """<!doctype html><html lang="en"><head>
<title>Best Running Shoes for Flat Feet 2026 | ShoeLab</title>
<meta name="description" content="Running shoes for flat feet, tested over 500 miles: stability, cushioning, and value picks so your arches stop aching on long runs.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="https://example.com/shoes/flat-feet">
<meta property="og:title" content="Best Running Shoes for Flat Feet"><meta property="og:description" content="x"><meta property="og:image" content="https://example.com/i.png">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"x"}</script>
</head><body>
<h1>Best Running Shoes for Flat Feet</h1>
<p>Running shoes for flat feet need real support. We ran five hundred miles in twelve pairs to find the ones that keep arches happy. Each pair was worn on road and trail.</p>
<h2>How we tested</h2>
<p>""" + " ".join(["Every shoe was worn for at least forty miles on mixed roads and trails, then checked for wear."] * 20) + """</p>
<img src="/img/hero-shoes.jpg" alt="Runner wearing stability shoes">
<a href="/shoes/overpronation">Shoes for overpronation</a>
<a href="https://other.example.org/x">Source</a>
</body></html>"""

BAD_HTML = """<html><head></head><body><h1>One</h1><h1>Two</h1><p>Short.</p><img src="/a/b/red-car-01.png"><a href="/x">click here</a></body></html>"""
