# RankOS backend

FastAPI + async SQLAlchemy. Seven agents pass work through a DB-backed job queue; every change
lands on the dashboard for approval before anything is pushed.

```
Crawler → Auditor → Keyword Scout → Fixer ─(you approve)→ Publisher (branch/PR) → Verifier
                                                                                     ↑
Ranker (daily Search Console sync, drop detection, blames recent change sets) ───────┘
Migration Advisor: old site vs new site → URL map, 301s, gaps, staged plan (on demand)
```

## Run

```bash
cd backend
uv sync
cp .env.example .env            # NETWORK_ENABLED=false by default: nothing leaves this machine
uv run uvicorn app.main:app --reload --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- SQLite at `./data/rankos.db` by default; set `DATABASE_URL=postgresql+asyncpg://…` for Postgres.
- Worker + scheduler run inside the API process (`WORKER_ENABLED=true`); or run them apart with
  `uv run python -m app.worker`.

## Switch on integrations

Each one needs `NETWORK_ENABLED=true` **and** its own credential; otherwise the agent falls back
(heuristic copy instead of the OpenAI model, on-page signals instead of Search Console, manual apply instead of PR).

| Integration | Env | Used by |
|---|---|---|
| Crawling the site | `NETWORK_ENABLED` | Crawler, Verifier, Migration Advisor |
| OpenAI (`OPENAI_MODEL`, default `sol`) | `OPENAI_API_KEY` | Fixer (copy), Keyword Scout (intent/new terms), Migration Advisor (narrative) |
| Search Console | `GSC_SERVICE_ACCOUNT_JSON` + site `gsc_property` | Ranker, Keyword Scout, Fixer (traffic weighting) |
| Local repo | `REPO_LOCAL_PATH` | Publisher (branch + commit) |
| GitHub | `GITHUB_TOKEN` + site `repo` | Publisher (push + PR), Verifier (merge status) |

## Main endpoints (`/api`)

- `POST /sites` · `GET /sites/{id}/overview` · `POST /sites/{id}/crawl` · `POST /sites/{id}/rank-sync`
- `GET /sites/{id}/pages` · `GET /pages/{id}` · `GET /sites/{id}/issues` · `GET /rules`
- `GET /sites/{id}/keywords` · `GET /keywords/{id}/history` · `GET /sites/{id}/analytics/trend` · `…/score-history`
- `GET /sites/{id}/change-sets` · `GET /change-sets/{id}` · `POST …/approve` · `…/reject` · `…/mark-applied` · `PATCH /changes/{id}`
- `POST /sites/{id}/migrations` · `GET /migrations/{id}` · `PATCH /migrations/{id}/steps/{n}`
- `GET /sites/{id}/jobs` · `GET /sites/{id}/events` · `GET /sites/{id}/events/stream` (SSE) · `GET /agents`

## Tests

```bash
uv run pytest
```
