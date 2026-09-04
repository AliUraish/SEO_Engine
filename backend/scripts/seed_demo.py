"""Local-dev seed: a site with crawled pages, Search Console history and one audit run — no network.

    uv run python scripts/seed_demo.py

Safe to re-run; it creates a fresh site each time."""

from __future__ import annotations

import asyncio
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawler.parse import FetchMeta, parse_html  # noqa: E402
from app.db.base import Database, utcnow  # noqa: E402
from app.db.models import Crawl, Keyword, Page, Ranking, Site  # noqa: E402
from app.queue.jobs import JobQueue  # noqa: E402
from app.util.urls import safe_path  # noqa: E402

ORIGIN = "https://demo-shoes.example"

BODY = " ".join(["We tested every pair on road and trail for at least forty miles, then checked wear, cushioning and support."] * 18)


def page(path: str, title: str | None, desc: str | None, h1: list[str], extra: str = "", words: str = BODY) -> str:
    head = "".join(
        [
            f"<title>{title}</title>" if title else "",
            f'<meta name="description" content="{desc}">' if desc else "",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<link rel="canonical" href="{ORIGIN}{path}">',
            extra,
        ]
    )
    h1s = "".join(f"<h1>{h}</h1>" for h in h1)
    links = "".join(f'<a href="{p}">{t}</a>' for p, t in [("/", "Home"), ("/shoes/flat-feet", "Flat feet"), ("/shoes/trail", "Trail"), ("/blog/lacing", "Lacing guide")] if p != path)
    return f'<html lang="en"><head>{head}</head><body>{h1s}<h2>How we tested</h2><p>{words}</p><img src="/img/hero.jpg" alt="Runner"><img src="/img/pair-01.jpg">{links}</body></html>'


PAGES = [
    ("/", "Running shoes tested by runners | ShoeLab", "Honest running shoe reviews from 500-mile tests: stability, cushioning and value picks for every foot type.", ["Running shoes, tested properly"]),
    ("/shoes/flat-feet", "Best Running Shoes for Flat Feet 2026 | ShoeLab", "Running shoes for flat feet, tested over 500 miles: stability, cushioning and value picks so your arches stop aching.", ["Best Running Shoes for Flat Feet"]),
    ("/shoes/trail", "Trail shoes", None, ["Trail running shoes", "Our picks"]),
    ("/shoes/wide", None, None, []),
    ("/blog/lacing", "Lacing guide | ShoeLab", "A lacing guide.", ["How to lace running shoes for heel slip, wide feet and high arches"]),
    ("/blog/old-post", "Trail shoes", "Running shoes for flat feet, tested over 500 miles: stability, cushioning and value picks so your arches stop aching.", ["Old post"]),
]

QUERIES = [
    ("running shoes for flat feet", "/shoes/flat-feet", 7.5, 900),
    ("best stability running shoes", "/shoes/flat-feet", 12.0, 600),
    ("trail running shoes", "/shoes/trail", 18.0, 1400),
    ("how to lace running shoes", "/blog/lacing", 4.0, 700),
    ("shoelab", "/", 1.2, 300),
    ("wide running shoes", "/shoes/wide", 28.0, 500),
    ("heel slip running shoes", "/blog/lacing", 9.0, 250),
    ("running shoes overpronation", "/shoes/flat-feet", 15.0, 420),
]


async def main() -> None:
    db = Database()
    await db.create_all()
    queue = JobQueue(db)
    random.seed(7)
    async with db.session() as s:
        site = Site(name="ShoeLab (demo)", url=ORIGIN, gsc_property=f"sc-domain:{ORIGIN.split('//')[1]}", settings={"focus_keywords": {"/shoes/flat-feet": "running shoes for flat feet", "/shoes/trail": "trail running shoes"}})
        s.add(site)
        await s.flush()
        crawl = Crawl(site_id=site.id, status="done", started_at=utcnow(), finished_at=utcnow(), pages_found=len(PAGES), stats={"ok": len(PAGES), "avg_ttfb_ms": 320})
        s.add(crawl)
        await s.flush()
        for path, title, desc, h1 in PAGES:
            html = page(path, title, desc, h1, words=BODY if path != "/shoes/wide" else "Coming soon.")
            snap = parse_html(html, FetchMeta(url=ORIGIN + path, final_url=ORIGIN + path, status_code=200, content_type="text/html", ttfb_ms=random.randint(180, 950), bytes=len(html)))
            s.add(Page(site_id=site.id, url=snap.final_url, path=safe_path(snap.final_url), last_crawl_id=crawl.id, status_code=200, title=snap.title, meta_description=snap.meta_description, canonical=snap.canonical, h1=snap.h1, word_count=snap.word_count, snapshot=snap.model_dump(), fetched_at=utcnow()))

        today = date.today() - timedelta(days=2)
        for term, path, base_pos, base_imp in QUERIES:
            k = Keyword(site_id=site.id, term=term, source="gsc", tracked=term != "shoelab")
            s.add(k)
            await s.flush()
            for d in range(35, -1, -1):
                day = today - timedelta(days=d)
                drift = math.sin(d / 5) * 1.5 + (2.5 if term == "wide running shoes" and d < 7 else 0) - (0.06 * (35 - d) if term == "trail running shoes" else 0)
                pos = max(1.0, round(base_pos + drift + random.uniform(-0.6, 0.6), 1))
                imp = int(base_imp / 30 * random.uniform(0.7, 1.3))
                ctr = max(0.005, 0.32 * math.exp(-0.22 * pos))
                s.add(Ranking(site_id=site.id, keyword_id=k.id, page_url=ORIGIN + path, day=day, position=pos, clicks=int(imp * ctr), impressions=imp, ctr=ctr))
        await s.commit()
        site_id, crawl_id = site.id, crawl.id

    # audit → scout → fixer run through the real worker when the API is up
    await queue.enqueue("audit.crawl", {"site_id": str(site_id), "crawl_id": str(crawl_id)}, site_id=site_id)
    await db.close()
    print(f"seeded site {site_id}; start the API (worker on) and the audit → scout → fixer chain will run")


if __name__ == "__main__":
    asyncio.run(main())
