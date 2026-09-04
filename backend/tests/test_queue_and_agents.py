"""End-to-end without network: pages are seeded as if crawled, then Auditor → Scout → Fixer run
through the real queue/worker, a change set is approved via the API, and the Publisher reports
manual application because no repo is configured."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.db.models import AgentEvent, ChangeSet, Issue, Job, Page, Site
from app.queue.worker import Worker
from tests.conftest import BAD_HTML, GOOD_HTML, snap


async def _seed(db):
    async with db.session() as s:
        site = Site(name="ShoeLab", url="https://example.com", settings={"focus_keywords": {"/bad": "red car"}})
        s.add(site)
        await s.flush()
        from app.db.models import Crawl

        crawl = Crawl(site_id=site.id, status="done", started_at=utcnow(), finished_at=utcnow(), pages_found=2)
        s.add(crawl)
        await s.flush()
        for url, html in (("https://example.com/", GOOD_HTML), ("https://example.com/bad", BAD_HTML)):
            sn = snap(url, html)
            s.add(Page(site_id=site.id, url=url, path=url.replace("https://example.com", "") or "/", last_crawl_id=crawl.id, status_code=200, title=sn.title, snapshot=sn.model_dump(), fetched_at=utcnow()))
        await s.commit()
        return site.id, crawl.id


async def _drain(worker, max_jobs=10):
    n = 0
    while n < max_jobs and await worker.run_once():
        n += 1
    return n


async def test_queue_claim_complete_fail_backoff(db, queue):
    j = await queue.enqueue("crawl.site", {"site_id": "x"}, max_attempts=2)
    claimed = await queue.claim("w1")
    assert claimed and claimed.id == j.id and claimed.status == "running" and claimed.attempts == 1
    assert await queue.claim("w2") is None
    assert await queue.fail(claimed, "boom") == "retry"
    again = await queue.get(j.id)
    assert again.status == "queued" and again.run_at > utcnow() + timedelta(seconds=30)
    again.run_at = utcnow() - timedelta(seconds=1)
    async with db.session() as s:
        row = await s.get(Job, j.id)
        row.run_at = utcnow() - timedelta(seconds=1)
        await s.commit()
    c2 = await queue.claim("w1")
    assert c2 and c2.attempts == 2
    assert await queue.fail(c2, "boom again") == "dead"
    assert (await queue.get(j.id)).status == "failed"
    j2 = await queue.enqueue("rank.sync", {})
    assert await queue.cancel(j2.id) is True and (await queue.get(j2.id)).status == "cancelled"


async def test_audit_scout_fix_pipeline_and_approval(db, queue, integrations, client):
    site_id, crawl_id = await _seed(db)
    worker = Worker(db, queue, integrations, concurrency=1)
    await queue.enqueue("audit.crawl", {"site_id": str(site_id), "crawl_id": str(crawl_id)}, site_id=site_id)
    ran = await _drain(worker)
    assert ran == 3  # audit → scout → fix

    async with db.session() as s:
        jobs = (await s.scalars(select(Job).order_by(Job.created_at))).all()
        assert [j.type for j in jobs] == ["audit.crawl", "keywords.scout", "fix.propose"]
        assert all(j.status == "done" for j in jobs), [(j.type, j.error) for j in jobs]
        pages = {p.path: p for p in (await s.scalars(select(Page))).all()}
        assert pages["/"].score >= 90 and pages["/bad"].score < 40
        issues = (await s.scalars(select(Issue).where(Issue.site_id == site_id))).all()
        assert any(i.rule_code == "TITLE_MISSING" for i in issues)
        cs = await s.scalar(select(ChangeSet))
        assert cs and cs.status == "pending_approval" and cs.expected_impact > 0
        handoffs = (await s.scalars(select(AgentEvent).where(AgentEvent.level == "handoff"))).all()
        assert {e.agent for e in handoffs} == {"auditor", "keyword-scout"}

    # dashboard flow via API
    r = await client.get(f"/api/sites/{site_id}/overview")
    assert r.status_code == 200 and r.json()["pending_change_sets"] == 1 and r.json()["open_issues"] > 0
    r = await client.get(f"/api/sites/{site_id}/change-sets")
    cs_id = r.json()[0]["id"]
    detail = (await client.get(f"/api/change-sets/{cs_id}")).json()
    assert detail["changes"] and {c["kind"] for c in detail["changes"]} <= {"title", "meta_description", "alt_text"}
    first = detail["changes"][0]
    r = await client.patch(f"/api/changes/{first['id']}", json={"after": "Hand-edited title | ShoeLab"})
    assert r.status_code == 200 and r.json()["generated_by"] == "user"
    r = await client.post(f"/api/change-sets/{cs_id}/approve", json={"note": "looks good"})
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # publisher runs: no repo configured → awaiting manual, verification queued after mark-applied
    assert await _drain(worker) == 1
    r = await client.get(f"/api/change-sets/{cs_id}")
    assert r.json()["status"] == "awaiting_manual" and all(c["apply_status"] == "needs_manual" for c in r.json()["changes"])
    r = await client.post(f"/api/change-sets/{cs_id}/mark-applied", json={})
    assert r.json()["status"] == "merged"
    async with db.session() as s:
        v = await s.scalar(select(Job).where(Job.type == "verify.changeset"))
        assert v and v.status == "queued"

    # second fix.propose does not stack a new change set while one is in flight
    await queue.enqueue("fix.propose", {"site_id": str(site_id)}, site_id=site_id)
    await _drain(worker, 1)
    async with db.session() as s:
        assert len((await s.scalars(select(ChangeSet))).all()) == 1


async def test_network_gate_blocks_crawl(db, queue, integrations):
    async with db.session() as s:
        site = Site(name="x", url="https://example.com")
        s.add(site)
        await s.commit()
        sid = site.id
    worker = Worker(db, queue, integrations, concurrency=1)
    await queue.enqueue("crawl.site", {"site_id": str(sid)}, site_id=sid, max_attempts=1)
    await worker.run_once()
    async with db.session() as s:
        job = await s.scalar(select(Job))
        assert job.status == "failed" and "Network is disabled" in job.error
        ev = await s.scalar(select(AgentEvent).where(AgentEvent.level == "error"))
        assert ev and "Network is disabled" in ev.message


async def test_site_crud_and_migration_enqueue(client, db):
    r = await client.post("/api/sites", json={"name": "Old", "url": "https://old.example.com/some/path"})
    assert r.status_code == 201 and r.json()["url"] == "https://old.example.com"
    sid = r.json()["id"]
    r = await client.patch(f"/api/sites/{sid}", json={"settings": {"rank_drop_threshold": 5}})
    assert r.json()["settings"]["rank_drop_threshold"] == 5
    r = await client.post(f"/api/sites/{sid}/migrations", json={"old_url": "https://old.example.com", "new_url": "https://new.example.com"})
    assert r.status_code == 202 and r.json()["status"] == "queued"
    r = await client.get(f"/api/sites/{sid}/jobs")
    assert [j["type"] for j in r.json()] == ["migration.plan"]
    r = await client.get("/api/agents")
    assert {a["name"] for a in r.json()} == {"crawler", "auditor", "keyword-scout", "fixer", "verifier", "ranker", "migration-advisor"}
    assert (await client.get("/api/rules")).json()[0]["code"] == "HTTP_ERROR"
    assert (await client.get(f"/api/sites/{uuid.uuid4()}")).status_code == 404
