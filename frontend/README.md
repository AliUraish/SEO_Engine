# RankOS frontend

React 19 + Vite + Tailwind v4 + framer-motion + TanStack Query + Recharts.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api → http://127.0.0.1:8000)
```

Start the backend first (`cd backend && uv run uvicorn app.main:app --reload`).
For a populated dashboard without any network access: `cd backend && uv run python scripts/seed_demo.py`, then start the API.

Pages: Overview · Keywords · Issues · Changes (approve / edit / reject) · Migration · Settings.
The activity icon in the top bar opens the live agent feed (SSE).
