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

Set `ANALYTICS_PASSWORD` (and optionally `ANALYTICS_USER`, default `admin`) to enable the operator endpoints. The legacy `ANALYTICS_SECRET` is still accepted as a password fallback when `ANALYTICS_PASSWORD` is unset.

## Architecture

### Identity and the monotonic-score invariant

`user_id` is the person; `name` is only a display label and is expected to change over time. The client generates `user_id` via `crypto.randomUUID()` on first visit and persists it in `localStorage` — there are no accounts and no auth on the game endpoints.

**Scores never decrease.** This invariant is enforced in two places and both must be preserved:

- server: `/pop` upserts with `count = GREATEST(scores.count, EXCLUDED.count)`
- client: `applyRecord()` only assigns the server's count when `d.count > count`

Because clients post an absolute cumulative total (not a delta), any change that makes the write authoritative rather than a max would let a stale or reset device wipe a player's progress.

### Public game API vs. protected operator API

Routes are split across two objects and **which one you decorate with decides whether the endpoint is authenticated**:

- `@app.*` — public, no auth: `GET /`, `POST /pop`, `GET /ranking`, `GET /ranking/{user_id}`. These four are exactly what `index.html` calls.
- `@admin_router.*` — HTTP Basic required: `/stats`, `/analytics/*`, `/dashboard`, and `DELETE /reset/{user_id}` (the only endpoint that can break the monotonic-score invariant). `admin_router = APIRouter(dependencies=[Depends(require_admin)])`, so anything added to it is protected automatically — that is the point of the grouping, and new operator endpoints belong here rather than on `app`.

`app.include_router(admin_router)` sits at the bottom of the file, just above `if __name__ == "__main__":`. Without that line every protected route silently 404s.

`require_admin` is **fail-closed**: with neither `ANALYTICS_PASSWORD` nor `ANALYTICS_SECRET` set it returns 503 rather than allowing access. It rejects at request time, not import time, so a missing env var takes down the dashboard but leaves the game API serving. Credentials are compared with `secrets.compare_digest`, and `HTTPBasic(auto_error=False)` is deliberate — the default would emit 401 before the config check could distinguish "not configured" (503) from "wrong password" (401).

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


## 커밋 컨벤션
- **main에 직접 커밋하지 않는다.** 항상 새 브랜치를 파서 작업하고, PR을 통해 main에 병합한다.
- 커밋 메시지는 Conventional Commits 형식(feat/fix/docs/chore...), 제목은 한 줄, 본문에 "왜"를 적는다. (`/commit` 슬래시 커맨드 참고)

## 운영 의도
- 프론트(index.html)는 Vercel에 별도 호스팅. 이 서버는 API 전용.
- /dashboard 는 배포 기능이 아니라 개발자(나) 혼자 보는 운영 도구. 외부 공개 계획 없음.

- 이 DB는 무료 티어라 30일마다 만료됨(현재 만료 ~8/21). 만료 알림 수신 시 즉시 pg_dump로 백업 후 조치.