# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

POPKEMON is a click-counter game with a global leaderboard. The whole product is two files:

- `server_deploy.py` — the entire FastAPI backend (game API + analytics module + an inlined HTML dashboard)
- `index.html` — the entire frontend (markup, CSS, and game JS in one file, no build step)

There is no test suite, no linter config, and no package manifest beyond `requirements.txt`. Don't look for one — commands like `npm test` or `pytest` have nothing to run.

## Commands

```bash
pip install -r requirements.txt

# DATABASE_URL is mandatory — the module raises RuntimeError at import time without it.
export DATABASE_URL='postgresql://...'
python server_deploy.py           # serves on $PORT, default 8000
```

Interactive API docs (FastAPI-generated) are at `/docs`. Deployment is Render, which injects `PORT` and `DATABASE_URL` and runs the ASGI target `server_deploy:app`.

Optional: set `ANALYTICS_SECRET` to require `?key=<secret>` on every `/analytics/*` and `/dashboard` request. When unset, those endpoints are fully public.

## Architecture

### Identity and the monotonic-score invariant

`user_id` is the person; `name` is only a display label and is expected to change over time. The client generates `user_id` via `crypto.randomUUID()` on first visit and persists it in `localStorage` — there are no accounts and no auth on the game endpoints.

**Scores never decrease.** This invariant is enforced in two places and both must be preserved:

- server: `/pop` upserts with `count = GREATEST(scores.count, EXCLUDED.count)`
- client: `applyRecord()` only assigns the server's count when `d.count > count`

Because clients post an absolute cumulative total (not a delta), any change that makes the write authoritative rather than a max would let a stale or reset device wipe a player's progress.

### Two tables, two very different roles

- `scores` — one row per `user_id`, the current state. Small, read by the leaderboard.
- `pop_logs` — append-only, one row per sync. This is the *only* history the analytics layer has, so every derived metric is reconstructed from it.

`pop_logs.time` is a **TEXT column** holding `datetime.now().isoformat()`. Analytics casts it and interprets it as UTC (`AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Seoul'`) to bucket by Korean calendar day. That is correct on Render (UTC containers) but wrong when logs are written from a non-UTC machine, which silently shifts day boundaries. Keep writing ISO-format naive UTC timestamps.

Old logs are pruned opportunistically: `/pop` uses the `RETURNING id` from its own insert and runs a `DELETE` only when `new_id % CLEANUP_EVERY_N_POPS == 0`, avoiding a periodic `COUNT(*)`. The delete is wrapped in `try` so cleanup failure never breaks a pop.

### Two independent DB access paths

The game endpoints borrow from a `psycopg_pool.ConnectionPool` (`get_db()`, `max_size=8` because free-tier Postgres connection limits are tight). The analytics module instead calls `_analytics_query()`, which opens a **fresh `psycopg.connect()` per query** and bypasses the pool entirely. `/dashboard` and `/analytics/user/{id}` issue several such queries per request, so these endpoints are connection-hungry — prefer the pool for anything new, and be careful about adding analytics calls to hot paths.

### Derived analytics concepts

- A **session ("방문")** is not tracked; it is inferred from gaps in `pop_logs` — a gap longer than `SESSION_GAP_MINUTES` (30) starts a new one. The constant is interpolated into SQL string literals in two separate queries.
- **`clicks_gained`** is a per-day delta reconstructed from cumulative counts via `LAG()`, since only running totals are stored.
- `_users_data()` returns *all* users unpaginated; `/analytics/user/{user_id}` filters that full list in Python rather than querying one user.

### Dashboard rendering

`/dashboard` is server-rendered by string-replacing the `/*DAILY_JSON*/` and `/*USERS_JSON*/` comment markers inside the `_DASHBOARD_HTML` template with `json.dumps(...)` output. The markers are inside a `<script>` block, so they must remain valid JS expression positions — renaming or reformatting them breaks the page silently.

### Frontend ↔ backend coupling

`index.html` hardcodes `const API = 'https://popketmon-server.onrender.com'`. **Opening `index.html` locally still reads and writes the production database.** Point `API` at `http://localhost:8000` before testing anything that writes.

`GET /` serves the game page by opening a **hardcoded filename** from the process working directory. That filename must match the page actually committed here (`index.html`), and the server must be started from the repo root — a mismatch turns the root route into a `FileNotFoundError` while every API route keeps working, so it is easy to miss.

Sync cadence, which shapes the analytics data: the client posts to `/pop` only every 5th click (`count % 5 === 0`), and polls `/ranking` every 30 seconds. One `pop_logs` row therefore represents a batch of clicks, not one click — `count` is the cumulative total at sync time.

## Constraints worth remembering

- Free Render Postgres instances expire ~30 days after creation; the data must be migrated or backed up before then.
- Render's web filesystem is ephemeral, which is why storage moved from SQLite to Postgres. Never reintroduce local-file persistence for anything that must survive a restart.
- CORS is `allow_origins=["*"]` and there is no rate limiting or server-side validation of submitted counts — a client can post any number. Treat leaderboard values as untrusted.
- Code comments and user-facing strings are in Korean; match that when editing.
