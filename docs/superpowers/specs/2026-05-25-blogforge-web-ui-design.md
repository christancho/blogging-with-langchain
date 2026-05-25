# BlogForge Web UI — Design Spec

**Date:** 2026-05-25  
**Status:** Approved

## Overview

Add a hosted web UI to the existing LangGraph blog generation system. The UI removes terminal friction, provides a topic queue so posts can be batched, and includes a preview gate before anything goes to Ghost CMS.

The existing Python codebase (`graph.py`, `nodes/`, `tools/`, `prompts/`) is untouched. New code wraps it with a FastAPI layer and a Next.js frontend.

---

## Architecture

Three services, deployed to Railway or Render:

```
Browser (Next.js)
      ↕  HTTPS — REST + polling
FastAPI Backend (Python)
      ├── Background Worker  →  LangGraph pipeline (existing code)
      └── PostgreSQL (managed by PaaS)
                              ↓ on publish approval
                         Ghost CMS (existing integration)
```

**FastAPI** runs alongside the existing code. It imports `create_blog_graph()` directly — no subprocess, no HTTP between them.

**Next.js** is a separate service. It calls the FastAPI REST API. No server-side rendering of blog content needed — all API calls are client-side from the dashboard.

**PostgreSQL** stores the job queue and results. Managed instance provided by Railway/Render — no self-hosted Postgres.

---

## Repository Layout

New directories added to the existing repo root:

```
api/
  main.py           # FastAPI app entrypoint, login route, CORS config
  worker.py         # Background thread: polls DB, runs LangGraph jobs
  models.py         # SQLAlchemy Job model
  db.py             # Async Postgres connection (asyncpg + SQLAlchemy)
  auth.py           # JWT creation, verification, password hashing
  routes/
    jobs.py         # CRUD + publish endpoint
    settings.py     # Read/write default tone, word count
  alembic/          # DB migrations
    env.py
    versions/

web/
  app/
    (auth)/
      login/
        page.tsx
    (dashboard)/
      layout.tsx        # Tab nav + auth check
      new-post/
        page.tsx
      queue/
        page.tsx
      history/
        page.tsx
      history/[id]/
        page.tsx        # Full preview + publish screen
      settings/
        page.tsx
  middleware.ts         # JWT cookie guard — blocks all dashboard routes
  lib/
    api.ts              # Typed fetch wrappers for FastAPI endpoints
```

Existing files that change:

- `requirements.txt` — add `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `python-jose[cryptography]`, `passlib[bcrypt]`
- `.env.example` — add `DATABASE_URL`, `JWT_SECRET`, `UI_PASSWORD`
- `.gitignore` — add `.superpowers/`

---

## Database

Two tables: `jobs` and `settings`.

The `settings` table holds a single row: `default_tone`, `default_word_count`, `password_hash`. On first API startup, if the table is empty, the row is seeded from `UI_PASSWORD` (plaintext) in `.env` — hashed with bcrypt before storing. After that, `UI_PASSWORD` is ignored; the Settings tab manages the password.

### `jobs` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | generated |
| `topic` | TEXT | required |
| `tone` | TEXT | defaults to `Config.BLOG_TONE` |
| `word_count` | INTEGER | defaults to `Config.WORD_COUNT_TARGET` |
| `instructions` | TEXT | nullable |
| `status` | TEXT | `pending`, `running`, `completed`, `failed`, `published` |
| `created_at` | TIMESTAMPTZ | set on insert |
| `started_at` | TIMESTAMPTZ | set when worker picks job |
| `completed_at` | TIMESTAMPTZ | set on terminal status |
| `current_node` | TEXT | updated by worker during run (for queue progress display) |
| `result` | JSONB | full `BlogState` on success, null otherwise |
| `error` | TEXT | error message on failure, null otherwise |

---

## Job Lifecycle

```
pending → running → completed → published
                 ↘ failed
```

- **pending**: in queue, waiting for worker
- **running**: worker is executing the LangGraph pipeline; `current_node` updated as each node completes
- **completed**: pipeline finished successfully; `result` JSONB contains full `BlogState`
- **failed**: pipeline threw an exception; `error` contains the message; retryable (re-inserts as new `pending` job)
- **published**: `POST /jobs/:id/publish` was called and Ghost accepted the post

---

## Background Worker

`api/worker.py` runs as a daemon thread started at FastAPI startup.

Behaviour:
1. Poll Postgres every 5 seconds for the oldest `pending` job
2. If found: set `status = running`, set `started_at`
3. Call `create_blog_graph().invoke(initial_state)` — synchronous, blocking the worker thread (this is intentional — one job at a time)
4. On success: set `status = completed`, write full `BlogState` to `result` JSONB, set `completed_at`
5. On exception: set `status = failed`, write error string to `error`, set `completed_at`
6. Loop back to step 1

The worker tracks the active node by calling `graph.stream(initial_state)` instead of `graph.invoke()`. LangGraph's stream yields a dict keyed by node name after each node completes — the worker reads this key and writes it to `current_node` in Postgres after each step. The final accumulated state is used as `result`.

One job runs at a time — no concurrency. This matches the existing CLI behaviour and avoids API rate-limit issues.

---

## API Endpoints

All endpoints require a valid JWT cookie except `POST /auth/login`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Accepts `{password}`, returns JWT cookie |
| POST | `/auth/logout` | Clears JWT cookie |
| GET | `/jobs` | List all jobs, ordered by `created_at` desc |
| POST | `/jobs` | Create job (adds to queue as `pending`) |
| GET | `/jobs/:id` | Get single job (includes `result` for preview) |
| DELETE | `/jobs/:id` | Remove job (only allowed if `status = pending`) |
| POST | `/jobs/:id/publish` | Publish to Ghost; sets `status = published` |
| POST | `/jobs/:id/retry` | Re-queue a `failed` job as new `pending` entry |
| GET | `/settings` | Get current defaults (tone, word count) |
| PUT | `/settings` | Update defaults |
| PUT | `/settings/password` | Change UI password; rotates JWT secret |

---

## Frontend

### Auth

`middleware.ts` intercepts all requests to `/(dashboard)/*`. If the JWT cookie is absent or expired, redirects to `/login`. The login page posts to `POST /auth/login` and on success redirects to `/queue`.

### Tab Navigation

Persistent tab bar across all dashboard pages: **New Post | Queue | History | Settings**. Active tab highlighted. A badge on the Queue tab shows the count of `pending + running` jobs.

### New Post Tab

Form fields:
- Topic (text input, required)
- Tone (text input, pre-filled from Settings default)
- Target word count (number input, pre-filled from Settings default)
- Custom instructions (textarea, optional)

Submit calls `POST /jobs`. On success, redirects to Queue tab.

### Queue Tab

Polls `GET /jobs` every 3 seconds.

- Running job (if any) shown at top with a progress bar and the value of `current_node`
- Pending jobs listed below in order, each with a Remove button (`DELETE /jobs/:id`)
- If queue is empty and no job is running, shows an empty state with a link to New Post

### History Tab

Shows all `completed`, `published`, and `failed` jobs, newest first.

- `completed` → yellow `READY TO REVIEW` badge + "Preview & Publish" button → navigates to `/history/:id`
- `published` → green `PUBLISHED` badge + "View on Ghost" link (opens Ghost URL in new tab)
- `failed` → red `FAILED` badge + error summary + Retry button (`POST /jobs/:id/retry`) + Dismiss button

### Preview & Publish Screen (`/history/:id`)

Full-page view. Fetches `GET /jobs/:id` to load `result` JSONB.

Displays:
- SEO title, meta description, excerpt
- Tags
- Word count, quality score, cost
- Full article rendered as Markdown (read-only)

Actions:
- **Publish to Ghost** button → calls `POST /jobs/:id/publish`, redirects to History on success
- **Discard** button → deletes the job record, redirects to History

### Settings Tab

Editable fields:
- Default tone (text input)
- Default word count (number input)
- Change password (two fields: new password + confirm)

Read-only integration status (derived from `Config`):
- Ghost CMS: connected / not configured
- Brave Search: connected / not configured
- Anthropic: connected / not configured

Save calls `PUT /settings`. Password change calls `PUT /settings/password`.

---

## Auth Design

- Password stored as a bcrypt hash in the `settings` table in Postgres
- On first startup, seeded from `UI_PASSWORD` (plaintext) in `.env` — hashed before storing; `UI_PASSWORD` is ignored after that
- `POST /auth/login` verifies password against the stored hash, returns a signed JWT as an `HttpOnly` cookie (7-day expiry)
- JWT signed with `JWT_SECRET` from `.env`
- `PUT /settings/password` updates the stored hash and rotates `JWT_SECRET`, invalidating all existing sessions
- No user accounts, no sign-up, no password reset flow (re-seed via `.env` + restart if locked out)

---

## Deployment (Railway or Render)

Two application services + one managed Postgres instance:

| Service | Runtime | Start command |
|---------|---------|---------------|
| `api` | Python 3.12 | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| `web` | Node 20 | `next start` |
| `db` | Managed Postgres | provided by platform |

Environment variables set in platform dashboard (not committed):

```
# api service
DATABASE_URL=postgresql+asyncpg://...
JWT_SECRET=<random 32 bytes>
UI_PASSWORD=<initial plaintext password — hashed and stored in DB on first run>
ANTHROPIC_API_KEY=...
BRAVE_API_KEY=...
GHOST_API_URL=...
GHOST_ADMIN_API_KEY=...
GHOST_AUTHOR_ID=...

# web service
NEXT_PUBLIC_API_URL=https://<api-service-url>
```

CORS on FastAPI is configured to allow requests only from the `web` service URL.

Alembic migrations run as a one-off command before the `api` service starts:
```
alembic upgrade head && uvicorn api.main:app ...
```

---

## Out of Scope

- Email or push notifications (the browser tab badge is the notification)
- Multiple user accounts
- Editing generated content in the UI before publishing
- Scheduling posts at a specific time (topic queue only)
- Dark/light mode toggle
