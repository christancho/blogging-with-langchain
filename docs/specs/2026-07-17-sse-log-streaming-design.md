# Design: Real-time pipeline log streaming (SSE + Postgres LISTEN/NOTIFY)

- **Issue:** [#17](https://github.com/christancho/blogging-with-langchain/issues/17)
- **Date:** 2026-07-17
- **Status:** Approved (brainstorming) — pending implementation plan

## Goal

Let a user watch the **live progress of a running LangGraph pipeline** in the web UI — the stdout each node prints (research sources found, writer drafting, fact-check pass/fail per claim, editor score/decision, revision loops) — streamed in real time instead of polled.

## Scope (v1)

**In scope:**
- Stream the existing **raw stdout log lines** of a running job to the browser, live.
- Transport: **Postgres `LISTEN`/`NOTIFY`** (per-run channel) → **SSE** → browser `EventSource`.
- Reconnect/replay from the existing durable `Job.logs` copy.

**Out of scope (v1):**
- Structured/typed events (node lifecycle, per-claim objects, editor score as data). v1 carries raw lines only.
- The job-**list** poll (`GET /jobs`). Left as-is; a separate concern.
- Redis. Deferred to a future scale-out phase (see issue #17).
- A `job_events` table. Not needed — `Job.logs` is the durable replay store for raw lines.

## Chosen approach: A′ — write-time publish

The pipeline runs synchronously (`graph.stream()` blocks the worker's event loop — the reason a separate log-flusher thread already exists). Rather than emit on a timer (poll-like) or via a DB trigger gated to the 2s write cadence, we publish each line **at the moment it is produced**:

- `TeeWriter.write()` enqueues each completed line into an in-memory `queue.Queue` (microseconds, non-blocking).
- A dedicated **publisher thread** drains the queue and fires `pg_notify` per line immediately — event-driven, sub-100ms, true push.
- The existing 2s `Job.logs` flush stays, but only for durable replay-on-reconnect; it is out of the live path.

Latency: A (timer flusher) ≈ 2s; B (trigger + refetch) ≈ 2s + a read per ping; **A′ ≈ instant, no extra reads.**

## Components

### 1. Line producer — `TeeWriter` (modified), `api/worker.py`
Already intercepts every `print()`. Change: split writes on newlines; push each **complete** line into a thread-safe `queue.Queue` tagged with a per-job monotonic `seq` (1, 2, 3… = the line's ordinal position in the log). Partial lines (no trailing `\n`) buffer until completed. Thread-safe for concurrent writes from the fact-checker's `ThreadPoolExecutor`.

### 2. Publisher thread — new, `api/worker.py`
Same lifecycle as today's log-flusher (started/stopped inside `_run_job`). Blocks on `queue.get()`; on each line fires:

```
pg_notify('blog_run_{job_id}', '{"seq": n, "line": "..."}')
```

Uses its own **sync `psycopg2`** connection (already a dependency), autocommit → each NOTIFY flushes immediately. On job end, publishes a terminal `{"done": true, "status": "completed|failed"}` event. NOTIFY/connection failures are **logged and swallowed** — they can never kill the job.

### 3. Durable replay copy — existing 2s `Job.logs` flush
Unchanged. Now serves only reconnect/replay; out of the live path.

### 4. SSE endpoint — new `GET /jobs/{job_id}/events`, `api/routes/jobs.py`
- Auth: existing `require_auth` cookie dependency (401 before the stream opens if unauthenticated).
- Returns `StreamingResponse` with media type `text/event-stream`.
- Opens a **dedicated asyncpg connection** (the pooled SQLAlchemy session cannot hold a `LISTEN`), `add_listener`s the run's channel.
- Emits a `: keep-alive` comment every ~15s.
- Cleans up (`remove_listener`, close connection) on client disconnect (`finally`).

### 5. Next.js streaming proxy — modify `web/app/api/proxy/[...path]/route.ts`
Today it buffers every response with `await res.arrayBuffer()`, which would break SSE. Add a branch: when the upstream response is `text/event-stream`, pass `res.body` (`ReadableStream`) straight through, with `export const dynamic = 'force-dynamic'` and no buffering.

### 6. Frontend — `web/lib/api.ts` + the log viewer
Replace the `/jobs/{id}/logs` poll with `new EventSource('/api/proxy/jobs/{id}/events')`. Cookie auth flows automatically (same-origin). Append lines live; close on the `done` event. Fall back to a one-shot `GET /jobs/{id}/logs` fetch if `EventSource` errors.

## Data flow

### Happy path (connected while running)
```
node print("✓ Research done")
 → TeeWriter.write() → enqueue {seq:42, line:"✓ Research done"}
   → Publisher thread → pg_notify('blog_run_<id>', '{"seq":42,...}')
     → Postgres broadcasts to every listener on the channel
       → SSE endpoint asyncpg callback → asyncio.Queue → `data: {...}\n\n`
         → Next proxy streams through → EventSource.onmessage → append
```

### Connect / reconnect replay (the seam)
Join the durable snapshot (`Job.logs`, up to 2s stale) to the live channel with no gaps/dupes. **Order matters:**

1. **Subscribe first** — `add_listener` and start buffering live events *before* reading `Job.logs`. Prevents a gap (a line published during setup is captured, not lost).
2. **Read the snapshot** — load `Job.logs`, emit as replay, and record threshold `k` = the number of **newline-terminated** lines (i.e. count of `\n`). Any trailing partial line (no final `\n`) is **not** counted, because the publisher only assigns a `seq` once a line completes — counting it would make `k` one too high and drop that line at the seam. The trailing partial text is still shown in the replay; its eventual completed line arrives live as `seq = k + 1`.
3. **Drain + go live** — forward buffered and subsequent live events, but **only `seq > k`**. Since `seq` = ordinal of completed lines and `Job.logs` holds exactly completed lines `1…k` in order, `seq > k` drops precisely the overlap — no gap, no dupe.
4. **Close** — on terminal `{"done": true}` (or job already terminal at connect), emit SSE `event: done` and close.

### Job finished before anyone connects
Step 2 replays full `Job.logs`; channel is silent; endpoint sees terminal `status` → emits `done` and closes. Zero live events.

### Multiple viewers of one run
Each connection has its own asyncpg listener + `asyncio.Queue`. `NOTIFY` broadcasts to all → every viewer gets every line, independently sequenced. Cost: one held-open PG connection per viewer (the acknowledged scaling limit).

### Concurrent jobs
Each on its own `blog_run_{id}` channel; a listener physically receives only its job's events. Worker is serial today so this won't occur yet, but the design and tests cover it at the channel layer.

## Error handling / edge cases

| Case | Handling |
|---|---|
| Publisher DB failure / NOTIFY error | Logged and swallowed in the publisher thread; never propagates to the pipeline. Live feed degrades; `Job.logs` + poll fallback still work. |
| Line > 8 KB (NOTIFY payload cap) | Publisher splits into <7 KB fragments sharing the `seq` plus a `frag` index; client concatenates. |
| Client disconnects mid-stream | `finally`: `remove_listener` + close asyncpg connection. Detected via request-disconnect / `asyncio.CancelledError`. |
| Job deleted mid-run | Worker stops at next node boundary; publisher emits terminal `done`; endpoint closes. |
| `Job.logs` is `NULL` (just started) | Replay empty (`k = 0`); all live lines forwarded. |
| Idle connection killed by a proxy | `: keep-alive` comment every ~15s. |
| SSE unsupported / EventSource error | Frontend falls back to one-shot `GET /jobs/{id}/logs`. |
| Auth mid-stream | Cookie checked at connect; 7-day token, so mid-stream expiry is a non-issue. |

## Cross-cutting notes

- **No schema migration.** Reuse `Job.logs`; no `job_events` table.
- **LISTEN/NOTIFY is runtime SQL** — nothing to migrate.
- **Channel name** `blog_run_<uuid>` = 45 chars, under PG's 63-char identifier limit. Use `pg_notify(text, text)` to avoid identifier quoting.
- **DSN form:** `DATABASE_URL` is SQLAlchemy-style (`postgresql+asyncpg://…`). The raw psycopg2 (publisher) and asyncpg (listener) connections must strip the `+asyncpg` suffix.

## Testing

- **Unit — `TeeWriter`:** partial lines buffer until `\n`; `seq` increments per completed line; thread-safe under concurrent writes.
- **Unit — publisher payload:** a >8 KB line splits into correct <7 KB `frag`s; normal lines pass through unchanged.
- **Integration (real Postgres via compose `db`, `pytest-asyncio`):**
  - Two listeners on one channel receive identical ordered lines (broadcast, no stealing).
  - Reconnect mid-stream replays `Job.logs` then continues — assert no gap, no dupe across the `seq > k` seam.
  - Two channels in parallel — zero cross-talk (isolation).
  - Terminal `done` event closes the stream.
- **Manual/e2e:** scripted `curl` check that the Next proxy streams `text/event-stream` incrementally (not buffered).

## Open items (deferred, not v1)

- Structured events + `job_events` table (issue #17 richer phase).
- Redis Streams for multi-worker scale-out.
- Streaming status changes to drop the job-list poll.
