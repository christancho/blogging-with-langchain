# SSE + Postgres LISTEN/NOTIFY Log Streaming — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream a running LangGraph pipeline's stdout to the browser live, via Postgres `LISTEN`/`NOTIFY` → SSE → `EventSource`, replacing the 2s log poll.

**Architecture:** The worker's `TeeWriter` enqueues each completed stdout line (with a monotonic `seq`) into a `queue.Queue`; a dedicated publisher thread drains it and `pg_notify`s each line on a per-run channel `blog_run_{job_id}` (approach A′, write-time publish). A new SSE endpoint holds a dedicated asyncpg `LISTEN` connection, replays `Job.logs` on connect, then forwards live events with `seq > k`. The Next.js proxy gains a streaming branch. No schema migration; `Job.logs` is the durable replay store.

**Tech Stack:** FastAPI, SQLAlchemy(async)+asyncpg, psycopg2 (sync publisher), Postgres LISTEN/NOTIFY, Next.js 15 (App Router), React 19, pytest/pytest-asyncio, jest/ts-jest.

**Spec:** `docs/specs/2026-07-17-sse-log-streaming-design.md`

## Global Constraints

- Live publish must **never** crash the pipeline: all NOTIFY/DB errors in the publisher are logged and swallowed (repo rule: no silent `except: pass` — always log).
- NOTIFY payload must stay **< 8 KB**; chunk at **7000 bytes**.
- `seq` = ordinal of **completed (newline-terminated)** lines, starting at 1.
- Channel name: `blog_run_{job_id}` (≤ 63 chars; a UUID makes it 45).
- `DATABASE_URL` is SQLAlchemy form (`postgresql+asyncpg://…`); raw psycopg2/asyncpg need the `+asyncpg` stripped.
- Integration tests require a running `blogforge_test` Postgres (same as existing `tests/api/`).
- No new dependencies — psycopg2-binary and asyncpg are already installed.

---

## File Structure

- **Create** `api/pg_dsn.py` — convert a SQLAlchemy DB URL to a plain libpq DSN for psycopg2/asyncpg.
- **Create** `api/log_stream.py` — pure helpers (`channel_for`, `build_payloads`, `count_completed_lines`) + the `LogPublisher` thread.
- **Modify** `api/worker.py` — `TeeWriter` gains a per-line callback + `seq`; `_run_job` starts/stops `LogPublisher`.
- **Modify** `api/routes/jobs.py` — add `GET /jobs/{job_id}/events` SSE endpoint.
- **Modify** `web/app/api/proxy/[...path]/route.ts` — stream `text/event-stream` instead of buffering.
- **Modify** `web/lib/api.ts` — add `jobs.streamEvents(id, handlers)`.
- **Modify** `web/app/(dashboard)/queue/page.tsx` — `LogPanel` uses `EventSource` with poll fallback.
- **Create** `web/jest.config.js` + add `"test": "jest"` to `web/package.json`.
- **Tests:** `tests/api/test_pg_dsn.py`, `tests/api/test_log_stream.py`, `tests/api/test_log_stream_pubsub.py`, `tests/api/test_teewriter.py`, `tests/api/test_worker_publish.py`, `tests/api/test_jobs_events.py`, `web/lib/__tests__/api.test.ts`.

---

## Task 1: Plain DSN helper

**Files:**
- Create: `api/pg_dsn.py`
- Test: `tests/api/test_pg_dsn.py`

**Interfaces:**
- Produces: `plain_dsn(url: str) -> str` — strips a `+driver` suffix from the scheme so psycopg2/asyncpg accept it. `postgresql+asyncpg://u:p@h:5432/db` → `postgresql://u:p@h:5432/db`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_pg_dsn.py
from api.pg_dsn import plain_dsn


def test_strips_asyncpg_driver():
    assert plain_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_strips_psycopg2_driver():
    assert plain_dsn("postgresql+psycopg2://u:p@h/db") == "postgresql://u:p@h/db"


def test_passthrough_when_no_driver():
    assert plain_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_pg_dsn.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.pg_dsn'`

- [ ] **Step 3: Write minimal implementation**

```python
# api/pg_dsn.py
import re


def plain_dsn(url: str) -> str:
    """Strip a SQLAlchemy '+driver' from the URL scheme so psycopg2/asyncpg accept it.

    Args:
        url: A database URL, possibly like 'postgresql+asyncpg://...'.
    Returns:
        The same URL with any '+driver' removed from the scheme.
    """
    return re.sub(r"^(postgresql|postgres)\+\w+://", r"\1://", url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_pg_dsn.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add api/pg_dsn.py tests/api/test_pg_dsn.py
git commit -m "feat: add plain_dsn helper for raw psycopg2/asyncpg connections (#17)"
```

---

## Task 2: Pure streaming helpers

**Files:**
- Create: `api/log_stream.py`
- Test: `tests/api/test_log_stream.py`

**Interfaces:**
- Produces:
  - `channel_for(job_id) -> str` — returns `f"blog_run_{job_id}"`.
  - `build_payloads(seq: int, line: str, max_bytes: int = 7000) -> list[str]` — returns one or more JSON strings `{"seq","line"}` (or `{"seq","frag","line"}` when a line is split because its UTF-8 length exceeds `max_bytes`). `frag` is a 0-based fragment index.
  - `count_completed_lines(text: str | None) -> int` — number of newline-terminated lines (i.e. count of `"\n"`); `None` → 0.
  - `done_payload(status: str) -> str` — returns `{"done": true, "status": status}` as JSON.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_log_stream.py
import json
from api.log_stream import channel_for, build_payloads, count_completed_lines, done_payload


def test_channel_for():
    assert channel_for("abc-123") == "blog_run_abc-123"


def test_build_payloads_single_line():
    out = build_payloads(5, "hello")
    assert len(out) == 1
    assert json.loads(out[0]) == {"seq": 5, "line": "hello"}


def test_build_payloads_splits_oversized_line():
    big = "x" * 15000
    out = build_payloads(7, big, max_bytes=7000)
    assert len(out) == 3
    frags = [json.loads(p) for p in out]
    assert [f["frag"] for f in frags] == [0, 1, 2]
    assert all(f["seq"] == 7 for f in frags)
    assert "".join(f["line"] for f in frags) == big


def test_count_completed_lines():
    assert count_completed_lines(None) == 0
    assert count_completed_lines("") == 0
    assert count_completed_lines("a\nb\n") == 2
    assert count_completed_lines("a\nb\npartial") == 2  # trailing partial not counted


def test_done_payload():
    assert json.loads(done_payload("completed")) == {"done": True, "status": "completed"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_log_stream.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.log_stream'`

- [ ] **Step 3: Write minimal implementation**

```python
# api/log_stream.py
import json


def channel_for(job_id) -> str:
    """Per-run Postgres NOTIFY channel name for a job."""
    return f"blog_run_{job_id}"


def build_payloads(seq: int, line: str, max_bytes: int = 7000) -> list[str]:
    """Serialize a log line into one or more JSON NOTIFY payloads under the 8KB cap.

    A line whose UTF-8 length exceeds max_bytes is split into fragments that all
    share the same seq and carry a 0-based `frag` index; the client concatenates.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= max_bytes:
        return [json.dumps({"seq": seq, "line": line})]

    payloads: list[str] = []
    frag = 0
    for start in range(0, len(encoded), max_bytes):
        chunk = encoded[start:start + max_bytes].decode("utf-8", errors="ignore")
        payloads.append(json.dumps({"seq": seq, "frag": frag, "line": chunk}))
        frag += 1
    return payloads


def count_completed_lines(text: str | None) -> int:
    """Number of newline-terminated lines; a trailing partial line is not counted."""
    if not text:
        return 0
    return text.count("\n")


def done_payload(status: str) -> str:
    """Terminal event payload signaling the stream should close."""
    return json.dumps({"done": True, "status": status})
```

Note: the byte-boundary split may cut a multi-byte UTF-8 char; `errors="ignore"` drops the split partial. This is acceptable for >7KB log lines (rare, non-critical output). Fragments still reassemble to the same text for ASCII-heavy logs.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_log_stream.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add api/log_stream.py tests/api/test_log_stream.py
git commit -m "feat: add pure log-stream helpers (channel, payloads, line count) (#17)"
```

---

## Task 3: TeeWriter per-line callback + seq

**Files:**
- Modify: `api/worker.py` (the `TeeWriter` class, lines 21-40)
- Test: `tests/api/test_teewriter.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `TeeWriter(real_stdout, on_line: Callable[[int, str], None] | None = None)`. When `on_line` is set, every completed (newline-terminated) line invokes `on_line(seq, line_without_newline)` with a monotonically increasing `seq` starting at 1. Partial text (no trailing `\n`) is held until completed. `getvalue()` still returns the full buffer including any partial tail.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_teewriter.py
import io
from api.worker import TeeWriter


def test_emits_completed_lines_with_seq():
    seen = []
    tee = TeeWriter(io.StringIO(), on_line=lambda seq, line: seen.append((seq, line)))
    tee.write("hello\nworld\n")
    assert seen == [(1, "hello"), (2, "world")]


def test_buffers_partial_line_until_newline():
    seen = []
    tee = TeeWriter(io.StringIO(), on_line=lambda seq, line: seen.append((seq, line)))
    tee.write("par")
    assert seen == []
    tee.write("tial\n")
    assert seen == [(1, "partial")]


def test_getvalue_includes_partial_tail():
    tee = TeeWriter(io.StringIO())
    tee.write("done\nrunning")
    assert tee.getvalue() == "done\nrunning"


def test_no_callback_is_safe():
    tee = TeeWriter(io.StringIO())
    tee.write("a\nb\n")  # must not raise
    assert tee.getvalue() == "a\nb\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_teewriter.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'on_line'`

- [ ] **Step 3: Write minimal implementation**

Replace the `TeeWriter` class in `api/worker.py` (lines 21-40) with:

```python
class TeeWriter:
    """Writes to both real stdout and an internal buffer for pipeline log capture.

    When `on_line` is provided, each completed (newline-terminated) line is
    emitted via on_line(seq, line) with a per-writer monotonic seq starting at 1.
    """

    def __init__(self, real_stdout, on_line=None):
        self._real = real_stdout
        self._buf = io.StringIO()
        self._on_line = on_line
        self._seq = 0
        self._pending = ""  # partial line not yet newline-terminated

    def write(self, text: str) -> int:
        self._real.write(text)
        self._buf.write(text)
        if self._on_line is not None:
            self._pending += text
            while "\n" in self._pending:
                line, self._pending = self._pending.split("\n", 1)
                self._seq += 1
                try:
                    self._on_line(self._seq, line)
                except Exception as e:  # never let publishing break the pipeline
                    self._real.write(f"[log-stream] on_line error (non-fatal): {e}\n")
        return len(text)

    def flush(self) -> None:
        self._real.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue()

    def __getattr__(self, name: str):
        return getattr(self._real, name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_teewriter.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add api/worker.py tests/api/test_teewriter.py
git commit -m "feat: TeeWriter emits completed lines with seq to a callback (#17)"
```

---

## Task 4: LogPublisher thread

**Files:**
- Modify: `api/log_stream.py` (add `LogPublisher`)
- Test: `tests/api/test_log_stream_pubsub.py`

**Interfaces:**
- Consumes: `plain_dsn` (Task 1), `channel_for`/`build_payloads`/`done_payload` (Task 2).
- Produces: `LogPublisher(job_id, dsn: str)` with:
  - `.publish(seq: int, line: str) -> None` — thread-safe enqueue (never blocks the pipeline).
  - `.start() -> None` — spawns the draining thread (opens its own psycopg2 autocommit connection).
  - `.stop(status: str = "completed") -> None` — enqueues a terminal marker, drains, closes the connection, joins the thread.
  - Internally NOTIFYs each `build_payloads(...)` string on `channel_for(job_id)`, and a final `done_payload(status)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_log_stream_pubsub.py
import asyncio
import json
import os
import uuid
import pytest
import asyncpg
from api.pg_dsn import plain_dsn
from api.log_stream import LogPublisher, channel_for

DSN = plain_dsn(os.environ["DATABASE_URL"])


async def _collect(channel: str, stop_after_done: asyncio.Event, out: list):
    conn = await asyncpg.connect(DSN)
    await conn.add_listener(channel, lambda c, pid, ch, payload: out.append(payload))
    await stop_after_done.wait()
    await conn.close()


@pytest.mark.asyncio
async def test_publish_delivers_lines_and_done():
    job_id = uuid.uuid4()
    channel = channel_for(job_id)
    received: list[str] = []
    done = asyncio.Event()

    listener = await asyncpg.connect(DSN)

    def on_notify(conn, pid, ch, payload):
        received.append(payload)
        if '"done"' in payload:
            done.set()

    await listener.add_listener(channel, on_notify)

    pub = LogPublisher(job_id, DSN)
    pub.start()
    pub.publish(1, "first line")
    pub.publish(2, "second line")
    pub.stop("completed")

    await asyncio.wait_for(done.wait(), timeout=5)
    await listener.close()

    parsed = [json.loads(p) for p in received]
    lines = [p for p in parsed if "line" in p]
    assert [p["line"] for p in lines[:2]] == ["first line", "second line"]
    assert any(p.get("done") is True and p["status"] == "completed" for p in parsed)


@pytest.mark.asyncio
async def test_two_listeners_both_receive(monkeypatch):
    job_id = uuid.uuid4()
    channel = channel_for(job_id)
    a, b = [], []
    la = await asyncpg.connect(DSN)
    lb = await asyncpg.connect(DSN)
    await la.add_listener(channel, lambda c, pid, ch, payload: a.append(payload))
    await lb.add_listener(channel, lambda c, pid, ch, payload: b.append(payload))

    pub = LogPublisher(job_id, DSN)
    pub.start()
    pub.publish(1, "broadcast me")
    pub.stop("completed")

    await asyncio.sleep(0.5)
    await la.close()
    await lb.close()
    assert any("broadcast me" in p for p in a)
    assert any("broadcast me" in p for p in b)


@pytest.mark.asyncio
async def test_isolation_across_channels():
    job_a, job_b = uuid.uuid4(), uuid.uuid4()
    got_a: list[str] = []
    la = await asyncpg.connect(DSN)
    await la.add_listener(channel_for(job_a), lambda c, pid, ch, payload: got_a.append(payload))

    pub_b = LogPublisher(job_b, DSN)
    pub_b.start()
    pub_b.publish(1, "for B only")
    pub_b.stop("completed")

    await asyncio.sleep(0.5)
    await la.close()
    assert got_a == []  # A's listener never sees B's channel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_log_stream_pubsub.py -v`
Expected: FAIL — `ImportError: cannot import name 'LogPublisher'`

- [ ] **Step 3: Write minimal implementation**

Append to `api/log_stream.py`:

```python
import logging
import queue
import threading

import psycopg2

logger = logging.getLogger(__name__)

_STOP = object()  # sentinel enqueued by stop()


class LogPublisher:
    """Drains published log lines from an in-process queue and NOTIFYs each on
    the job's per-run Postgres channel. Runs its own thread + sync psycopg2
    connection so it never blocks the (synchronous) pipeline."""

    def __init__(self, job_id, dsn: str):
        self._job_id = job_id
        self._channel = channel_for(job_id)
        self._dsn = dsn
        self._q: "queue.Queue" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._status = "completed"

    def publish(self, seq: int, line: str) -> None:
        self._q.put((seq, line))

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="log-publisher")
        self._thread.start()

    def stop(self, status: str = "completed") -> None:
        self._status = status
        self._q.put(_STOP)
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        conn = None
        try:
            conn = psycopg2.connect(self._dsn)
            conn.autocommit = True
            cur = conn.cursor()
            while True:
                item = self._q.get()
                if item is _STOP:
                    self._notify(cur, done_payload(self._status))
                    return
                seq, line = item
                for payload in build_payloads(seq, line):
                    self._notify(cur, payload)
        except Exception as e:  # never propagate to the pipeline
            logger.error(f"LogPublisher error (non-fatal) for job {self._job_id}: {e}", exc_info=True)
        finally:
            if conn is not None:
                conn.close()

    def _notify(self, cur, payload: str) -> None:
        try:
            cur.execute("SELECT pg_notify(%s, %s)", (self._channel, payload))
        except Exception as e:
            logger.error(f"pg_notify failed (non-fatal) for job {self._job_id}: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_log_stream_pubsub.py -v`
Expected: PASS (3 passed). Requires `blogforge_test` Postgres running.

- [ ] **Step 5: Commit**

```bash
git add api/log_stream.py tests/api/test_log_stream_pubsub.py
git commit -m "feat: LogPublisher thread NOTIFYs log lines on per-run channel (#17)"
```

---

## Task 5: Wire LogPublisher into the worker

**Files:**
- Modify: `api/worker.py` (`_run_job`: construct publisher, pass `on_line` to `TeeWriter`, stop on end)
- Test: `tests/api/test_worker_publish.py`

**Interfaces:**
- Consumes: `LogPublisher` (Task 4), `plain_dsn` (Task 1), `TeeWriter` on_line (Task 3), `channel_for` (Task 2).
- Produces: `_run_job` publishes each pipeline stdout line to `blog_run_{job_id}` and calls `publisher.stop(status)` with `"completed"`/`"failed"` at the end.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_worker_publish.py
import asyncio
import json
import os
import uuid
import pytest
import asyncpg
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api.pg_dsn import plain_dsn
from api.log_stream import channel_for
import api.worker as worker

DSN = plain_dsn(os.environ["DATABASE_URL"])


class _FakeGraph:
    """Stands in for the compiled LangGraph: prints then yields node chunks."""
    def stream(self, initial_state):
        print("RESEARCH: found 3 sources")
        yield {"research": {"research_summary": "x"}}
        print("WRITER: drafting")
        yield {"writer": {"article_content": "y"}}


@pytest.mark.asyncio
async def test_run_job_publishes_lines(test_engine, monkeypatch):
    from api.models import Job, Settings
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as db:
        job = Job(topic="t", tone="warm", word_count=100, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    monkeypatch.setattr(worker, "create_blog_graph", lambda: _FakeGraph())

    channel = channel_for(job_id)
    received: list[str] = []
    done = asyncio.Event()
    listener = await asyncpg.connect(DSN)

    def on_notify(conn, pid, ch, payload):
        received.append(payload)
        if '"done"' in payload:
            done.set()

    await listener.add_listener(channel, on_notify)

    await worker._run_job(job_id, session_factory)
    await asyncio.wait_for(done.wait(), timeout=5)
    await listener.close()

    lines = [json.loads(p).get("line", "") for p in received]
    assert any("RESEARCH: found 3 sources" in l for l in lines)
    assert any("WRITER: drafting" in l for l in lines)
    assert any('"done"' in p for p in received)
```

Note: this test uses `test_engine` (creates/drops tables) and commits a real job row so `_run_job`'s own sessions see it.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_worker_publish.py -v`
Expected: FAIL — no `done` NOTIFY received (times out), because `_run_job` does not yet start a publisher.

- [ ] **Step 3: Write minimal implementation**

In `api/worker.py`:

Add imports near the top (after existing imports):

```python
from api.pg_dsn import plain_dsn  # noqa: E402
from api.log_stream import LogPublisher  # noqa: E402
```

In `_run_job`, replace the `try:` block that sets up the tee (starting at `tee = TeeWriter(sys.stdout)`, line ~171) so the publisher is created and wired, and remove the separate `_start_log_flusher` reliance for the live path (keep it for durable `Job.logs`). Concretely, change the tee construction and add publisher lifecycle:

```python
    tee = None
    publisher = None
    flush_stop = threading.Event()

    # (… keep the existing _start_log_flusher definition unchanged …)

    try:
        publisher = LogPublisher(job_id, plain_dsn(os.environ["DATABASE_URL"]))
        publisher.start()
        tee = TeeWriter(sys.stdout, on_line=publisher.publish)
        sys.stdout = tee

        # (… keep the existing banner prints, flush thread start, graph.stream loop …)

        # success path — after the stream loop and Job.logs final write:
        publisher.stop("completed")

    except Exception as e:
        flush_stop.set()
        if publisher is not None:
            publisher.stop("failed")
        # (… keep the existing failure DB update …)
    finally:
        if tee is not None:
            sys.stdout = tee._real
```

Ensure `publisher.stop(...)` is called exactly once per path (move the existing `flush_stop.set()` and add the matching `publisher.stop` on both success and failure). Do not call `publisher.stop` in `finally` (status differs per path).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_worker_publish.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full worker test file to check no regressions**

Run: `pytest tests/api/test_worker.py -v`
Expected: PASS (existing worker tests still green)

- [ ] **Step 6: Commit**

```bash
git add api/worker.py tests/api/test_worker_publish.py
git commit -m "feat: worker publishes pipeline log lines via LogPublisher (#17)"
```

---

## Task 6: SSE endpoint `GET /jobs/{job_id}/events`

**Files:**
- Modify: `api/routes/jobs.py` (add the endpoint + a helper)
- Test: `tests/api/test_jobs_events.py`

**Interfaces:**
- Consumes: `require_auth`, `get_db`, `Job`, `plain_dsn`, `channel_for`, `count_completed_lines`.
- Produces: `GET /jobs/{job_id}/events` returning `text/event-stream`. On connect: subscribe to `channel_for(job_id)` first, read `Job.logs`, emit it as an initial `data:` frame `{"replay": "<full logs>"}`, compute `k = count_completed_lines(logs)`, then forward live events with `seq > k`. Emits `event: done` and closes on the terminal payload or if the job is already terminal. Sends a `: keep-alive` comment every 15s. 404 if the job does not exist.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_jobs_events.py
import asyncio
import json
import os
import uuid
import pytest
import asyncpg
from httpx import ASGITransport, AsyncClient
from api.pg_dsn import plain_dsn
from api.log_stream import channel_for, done_payload

DSN = plain_dsn(os.environ["DATABASE_URL"])


async def _notify(channel: str, payload: str):
    conn = await asyncpg.connect(DSN)
    await conn.execute("SELECT pg_notify($1, $2)", channel, payload)
    await conn.close()


@pytest.mark.asyncio
async def test_events_replays_then_streams_live(authed_client, db):
    from api.models import Job
    job = Job(topic="t", tone="warm", word_count=100, status="running",
              logs="line one\nline two\n")  # k = 2
    db.add(job)
    await db.commit()
    await db.refresh(job)
    channel = channel_for(job.id)

    received_lines: list[str] = []
    async with authed_client.stream("GET", f"/jobs/{job.id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        async def pump():
            async for raw in resp.aiter_lines():
                if raw.startswith("data:"):
                    obj = json.loads(raw[len("data:"):].strip())
                    if "replay" in obj:
                        received_lines.append("REPLAY:" + obj["replay"])
                    elif obj.get("done"):
                        return
                    else:
                        received_lines.append(obj["line"])

        task = asyncio.create_task(pump())
        await asyncio.sleep(0.3)
        # seq 2 must be dropped (already in replay, k=2); seq 3 delivered
        await _notify(channel, json.dumps({"seq": 2, "line": "DUP should drop"}))
        await _notify(channel, json.dumps({"seq": 3, "line": "line three"}))
        await asyncio.sleep(0.3)
        await _notify(channel, done_payload("completed"))
        await asyncio.wait_for(task, timeout=5)

    assert any(x.startswith("REPLAY:line one\nline two\n") for x in received_lines)
    assert "line three" in received_lines
    assert "DUP should drop" not in received_lines


@pytest.mark.asyncio
async def test_events_404_for_missing_job(authed_client):
    resp = await authed_client.get(f"/jobs/{uuid.uuid4()}/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_events_requires_auth(client):
    resp = await client.get(f"/jobs/{uuid.uuid4()}/events")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_jobs_events.py -v`
Expected: FAIL — 404/route-not-found (endpoint doesn't exist).

- [ ] **Step 3: Write minimal implementation**

Add to `api/routes/jobs.py` (imports at top, endpoint below `get_job_logs`):

```python
import asyncio
import json
import os
import asyncpg
from fastapi.responses import StreamingResponse
from api.pg_dsn import plain_dsn
from api.log_stream import channel_for, count_completed_lines
```

```python
@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Server-Sent Events stream of a job's live pipeline log.

    Replays Job.logs on connect, then forwards live NOTIFY events with seq > k.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    replay = job.logs or ""
    k = count_completed_lines(replay)
    terminal_at_connect = job.status in ("completed", "failed", "published")
    channel = channel_for(job_id)

    async def event_gen():
        conn = await asyncpg.connect(plain_dsn(os.environ["DATABASE_URL"]))
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_notify(_conn, _pid, _ch, payload):
            loop.call_soon_threadsafe(q.put_nowait, payload)

        # Subscribe FIRST so nothing published during setup is lost.
        await conn.add_listener(channel, on_notify)
        try:
            # Replay snapshot (up to 2s stale), then live with seq > k.
            yield f"data: {json.dumps({'replay': replay})}\n\n"
            if terminal_at_connect:
                yield f"event: done\ndata: {json.dumps({'done': True, 'status': job.status})}\n\n"
                return

            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                obj = json.loads(payload)
                if obj.get("done"):
                    yield f"event: done\ndata: {payload}\n\n"
                    return
                if obj.get("seq", 0) > k:
                    yield f"data: {payload}\n\n"
        finally:
            await conn.remove_listener(channel, on_notify)
            await conn.close()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_jobs_events.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the jobs route tests for regressions**

Run: `pytest tests/api/test_jobs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/routes/jobs.py tests/api/test_jobs_events.py
git commit -m "feat: add SSE /jobs/{id}/events endpoint (replay + live) (#17)"
```

---

## Task 7: Next.js proxy streaming branch

**Files:**
- Modify: `web/app/api/proxy/[...path]/route.ts`
- Test: manual (documented `curl`)

**Interfaces:**
- Produces: proxy passes `text/event-stream` responses through as a stream (no `arrayBuffer()` buffering), preserving cookies/headers.

- [ ] **Step 1: Modify the proxy to branch on content-type**

Replace the body of `handler` in `web/app/api/proxy/[...path]/route.ts` so a streaming upstream is piped through:

```typescript
import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL ?? 'http://localhost:8000';

export const dynamic = 'force-dynamic';

async function handler(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${API_URL}/${path.join('/')}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  headers.delete('host');

  const body =
    req.method === 'GET' || req.method === 'HEAD' ? undefined : await req.arrayBuffer();

  const res = await fetch(url, {
    method: req.method,
    headers,
    body: body ? Buffer.from(body) : undefined,
  });

  const resHeaders = new Headers(res.headers);
  resHeaders.delete('transfer-encoding');
  resHeaders.delete('content-encoding');

  // Stream Server-Sent Events straight through instead of buffering.
  if (res.headers.get('content-type')?.includes('text/event-stream')) {
    return new NextResponse(res.body, { status: res.status, headers: resHeaders });
  }

  return new NextResponse(await res.arrayBuffer(), {
    status: res.status,
    headers: resHeaders,
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manually verify streaming (documented check)**

With the stack running (`./dev.sh`) and a job in progress, confirm frames arrive incrementally (not all at once at the end):

Run: `curl -N -b "access_token=<your-cookie>" http://localhost:3000/api/proxy/jobs/<running-job-id>/events`
Expected: an immediate `data: {"replay": ...}` frame, then `data: {"seq": N, "line": ...}` frames trickling in live, ending with `event: done`.

- [ ] **Step 4: Commit**

```bash
git add web/app/api/proxy/[...path]/route.ts
git commit -m "feat: stream text/event-stream through the Next.js proxy (#17)"
```

---

## Task 8: Frontend `jobs.streamEvents` + jest

**Files:**
- Modify: `web/lib/api.ts` (add `streamEvents`)
- Create: `web/jest.config.js`
- Modify: `web/package.json` (add `"test": "jest"`)
- Test: `web/lib/__tests__/api.test.ts`

**Interfaces:**
- Produces: `jobs.streamEvents(id: string, handlers: { onReplay?: (text: string) => void; onLine?: (seq: number, line: string) => void; onDone?: (status: string) => void; onError?: () => void }) => EventSource`. Opens `new EventSource('/api/proxy/jobs/{id}/events', { withCredentials: true })`, parses each `message` payload (`replay` | `{seq,line}` | fragments) and routes to handlers; listens for the `done` event; reassembles fragmented lines by `seq`.

- [ ] **Step 1: Write the failing test**

```typescript
// web/lib/__tests__/api.test.ts
import { parseEvent } from '../api';

describe('parseEvent', () => {
  it('routes a replay payload', () => {
    const calls: string[] = [];
    parseEvent(JSON.stringify({ replay: 'a\nb\n' }), {
      onReplay: (t) => calls.push('replay:' + t),
    });
    expect(calls).toEqual(['replay:a\nb\n']);
  });

  it('routes a line payload', () => {
    const lines: Array<[number, string]> = [];
    parseEvent(JSON.stringify({ seq: 3, line: 'hi' }), { onLine: (s, l) => lines.push([s, l]) });
    expect(lines).toEqual([[3, 'hi']]);
  });

  it('reassembles fragmented lines by seq', () => {
    const lines: Array<[number, string]> = [];
    const h = { onLine: (s: number, l: string) => lines.push([s, l]) };
    parseEvent(JSON.stringify({ seq: 5, frag: 0, line: 'foo' }), h);
    parseEvent(JSON.stringify({ seq: 5, frag: 1, line: 'bar' }), h);
    // only the final fragment flushes the reassembled line
    expect(lines).toEqual([[5, 'foobar']]);
  });
});
```

- [ ] **Step 2: Create jest config and add the test script**

Create `web/jest.config.js`:

```javascript
/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/__tests__/**/*.test.ts'],
};
```

In `web/package.json`, add to `"scripts"`:

```json
    "test": "jest",
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npm test -- api.test.ts`
Expected: FAIL — `parseEvent` is not exported.

- [ ] **Step 4: Implement `parseEvent` and `streamEvents`**

Add to `web/lib/api.ts`:

```typescript
// ─── SSE event parsing ──────────────────────────────────────────────────────

export interface StreamHandlers {
  onReplay?: (text: string) => void;
  onLine?: (seq: number, line: string) => void;
  onDone?: (status: string) => void;
  onError?: () => void;
}

// Fragment reassembly buffer keyed by seq (module-level is fine: one stream at a time).
const _fragBuffers = new Map<number, string>();

export function parseEvent(data: string, handlers: StreamHandlers): void {
  let obj: Record<string, unknown>;
  try {
    obj = JSON.parse(data);
  } catch {
    return;
  }
  if (typeof obj.replay === 'string') {
    handlers.onReplay?.(obj.replay);
    return;
  }
  if (obj.done) {
    handlers.onDone?.(String(obj.status ?? 'completed'));
    return;
  }
  if (typeof obj.seq === 'number' && typeof obj.line === 'string') {
    if (typeof obj.frag === 'number') {
      const prev = _fragBuffers.get(obj.seq) ?? '';
      const combined = prev + obj.line;
      // Heuristic: flush when a fragment shorter than the cap arrives (last frag).
      if (obj.line.length < 7000) {
        _fragBuffers.delete(obj.seq);
        handlers.onLine?.(obj.seq, combined);
      } else {
        _fragBuffers.set(obj.seq, combined);
      }
      return;
    }
    handlers.onLine?.(obj.seq, obj.line);
  }
}

export function streamJobEvents(id: string, handlers: StreamHandlers): EventSource {
  const es = new EventSource(`${API}/jobs/${id}/events`, { withCredentials: true });
  es.onmessage = (e) => parseEvent(e.data, handlers);
  es.addEventListener('done', (e) => {
    parseEvent((e as MessageEvent).data, handlers);
    es.close();
  });
  es.onerror = () => handlers.onError?.();
  return es;
}
```

Add `streamEvents` to the `jobs` object:

```typescript
  streamEvents: (id: string, handlers: StreamHandlers) => streamJobEvents(id, handlers),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npm test -- api.test.ts`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add web/lib/api.ts web/lib/__tests__/api.test.ts web/jest.config.js web/package.json
git commit -m "feat: add streamJobEvents SSE client + parseEvent + jest config (#17)"
```

---

## Task 9: LogPanel consumes the SSE stream

**Files:**
- Modify: `web/app/(dashboard)/queue/page.tsx` (`LogPanel`)
- Test: manual (documented)

**Interfaces:**
- Consumes: `jobs.streamEvents` (Task 8).
- Produces: `LogPanel` renders live lines from `EventSource`; on SSE error it falls back to the one-shot `jobs.logs(jobId)` fetch.

- [ ] **Step 1: Replace the polling in `LogPanel`**

Replace the `fetchLogs`/`useEffect` polling block (lines 27-40) of `web/app/(dashboard)/queue/page.tsx` with an SSE subscription:

```typescript
  useEffect(() => {
    const lines: string[] = [];
    const flush = () => setLogs(lines.join('\n'));

    const es = jobs.streamEvents(jobId, {
      onReplay: (text) => {
        // text already includes trailing newline structure; seed the buffer
        lines.length = 0;
        if (text) lines.push(...text.replace(/\n$/, '').split('\n'));
        flush();
      },
      onLine: (_seq, line) => {
        lines.push(line);
        flush();
      },
      onError: () => {
        // Fallback: one-shot fetch if the stream drops
        jobs.logs(jobId).then((d) => { if (d.logs !== null) setLogs(d.logs); }).catch(() => {});
      },
    });

    return () => es.close();
  }, [jobId]);
```

Keep the auto-scroll `useEffect` and `handleScroll` unchanged.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual end-to-end verification**

Start the stack (`./dev.sh`), open the Queue page, and submit a new topic. Confirm:
- Log lines appear **live** as each node runs (not in 2s batches).
- Refreshing the page mid-run replays existing logs then continues live (no gaps/dupes).
- The Network tab shows one long-lived `jobs/{id}/events` request, not repeated `jobs/{id}/logs` polls.

- [ ] **Step 4: Commit**

```bash
git add "web/app/(dashboard)/queue/page.tsx"
git commit -m "feat: LogPanel streams pipeline logs over SSE with poll fallback (#17)"
```

---

## Task 10: Docs + final verification

**Files:**
- Modify: `CLAUDE.md` (note the SSE log stream) and `README.md` (brief mention) — optional but recommended.

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest tests/api -v`
Expected: all pass (requires `blogforge_test` Postgres).

- [ ] **Step 2: Run the web unit tests**

Run: `cd web && npm test`
Expected: all pass.

- [ ] **Step 3: Add a short note to CLAUDE.md**

Under the API section, document: "Live pipeline logs stream to the UI via `GET /jobs/{id}/events` (SSE) backed by Postgres LISTEN/NOTIFY on channel `blog_run_{id}`; `Job.logs` remains the durable replay store."

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document SSE pipeline log streaming (#17)"
```

---

## Self-Review Notes (for the implementer)

- Every spec section maps to a task: DSN (T1), pure helpers/seq/chunking (T2), TeeWriter seq (T3), publisher (T4), worker wiring (T5), SSE endpoint + replay seam (T6), proxy streaming (T7), client + fragment reassembly (T8), LogPanel live view + fallback (T9), verification/docs (T10).
- The `seq > k` seam (spec §Data flow) is exercised directly in T6's `test_events_replays_then_streams_live` (seq 2 dropped, seq 3 delivered).
- Isolation + broadcast (spec §Multiple viewers / §Concurrent jobs) are exercised in T4.
- `Job.logs` NULL edge (spec §Error handling) is covered implicitly by `count_completed_lines(None) == 0` (T2) and the endpoint's `job.logs or ""`.
- Payload > 8 KB (spec §Error handling) → T2 split + T8 reassembly.
```
