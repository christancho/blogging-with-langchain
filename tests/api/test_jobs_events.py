import asyncio
import json
import os
import socket
import subprocess
import sys
import uuid
import pytest
import pytest_asyncio
import asyncpg
from httpx import AsyncClient
from api.pg_dsn import plain_dsn
from api.log_stream import channel_for, done_payload

DSN = plain_dsn(os.environ["DATABASE_URL"])
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NOTE ON TEST STRATEGY:
# httpx==0.28.1's ASGITransport (used by the `client`/`authed_client` fixtures
# in conftest.py) does not support incremental streaming: it drives the whole
# ASGI app coroutine to completion and buffers the entire response body
# before `client.stream(...)` ever returns (verified empirically — see
# task-6-report.md). That's fine for every other route in this app, but it
# makes it impossible to test "connect, then receive live NOTIFY events
# while the connection is open" with those fixtures: the request would never
# return until our SSE generator's `while True` loop exits on its own, which
# is exactly what the test is trying to drive from the outside -> deadlock.
#
# So the two tests that need genuine interleaved streaming
# (test_events_replays_then_streams_live and
# test_events_terminal_fallback_without_done_notify) run the app in a real
# `uvicorn` subprocess and talk to it over a real TCP socket, where
# streaming works exactly as it does in production. They set up/tear down
# Job rows via raw asyncpg (autocommit) rather than the `db`/`authed_client`
# fixtures, because the subprocess has its own DB connections and cannot see
# the uncommitted transaction those fixtures keep test data inside.
#
# The remaining three tests (404, 401, already-terminal-at-connect) never
# need to observe a live NOTIFY mid-stream, so the ordinary in-process
# `authed_client`/`client` fixtures are used for them.


async def _notify(channel: str, payload: str):
    conn = await asyncpg.connect(DSN)
    await conn.execute("SELECT pg_notify($1, $2)", channel, payload)
    await conn.close()


async def _insert_job(job_id: uuid.UUID, status: str, logs: str) -> None:
    conn = await asyncpg.connect(DSN)
    await conn.execute(
        """
        INSERT INTO jobs (id, topic, tone, word_count, instructions, status, logs)
        VALUES ($1, 't', 'warm', 100, NULL, $2, $3)
        """,
        job_id, status, logs,
    )
    await conn.close()


async def _delete_job(job_id: uuid.UUID) -> None:
    conn = await asyncpg.connect(DSN)
    await conn.execute("DELETE FROM jobs WHERE id = $1", job_id)
    await conn.close()


async def _set_status(job_id: uuid.UUID, status: str) -> None:
    conn = await asyncpg.connect(DSN)
    await conn.execute("UPDATE jobs SET status = $1 WHERE id = $2", status, job_id)
    await conn.close()


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest_asyncio.fixture
async def live_server(test_engine):
    """Run the real app in a uvicorn subprocess bound to a free port.

    A separate OS process (rather than an in-process background thread) is
    used deliberately: `api.db.engine` is a module-level singleton whose
    asyncpg connections are bound to whatever event loop first uses them. A
    background thread would run its own event loop, and reusing the engine
    from a second loop within the same process risks
    "Future attached to a different loop" errors. A subprocess gets its own
    fresh interpreter, engine, and loop, matching how the app actually runs.

    Depends on `test_engine` (from conftest.py) purely for its side effect of
    creating the schema before this fixture starts the subprocess, and not
    dropping it until after the subprocess is killed — this fixture doesn't
    otherwise touch that engine/connection (the subprocess has its own).
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO_ROOT,
        env=env,
    )
    try:
        async with AsyncClient(base_url=base_url) as probe:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError(f"live server process exited early with code {proc.returncode}")
                try:
                    resp = await probe.get("/health", timeout=1)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError("live server did not become ready in time")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest_asyncio.fixture
async def authed_live_client(live_server):
    """AsyncClient hitting the real live_server, already logged in."""
    async with AsyncClient(base_url=live_server) as c:
        resp = await c.post("/auth/login", json={"password": os.environ.get("UI_PASSWORD", "testpass")})
        assert resp.status_code == 200, resp.text
        yield c


@pytest.mark.asyncio
async def test_events_replays_then_streams_live(authed_live_client):
    job_id = uuid.uuid4()
    await _insert_job(job_id, "running", "line one\nline two\n")  # k = 2
    channel = channel_for(job_id)

    received_lines: list[str] = []
    try:
        async with authed_live_client.stream("GET", f"/jobs/{job_id}/events") as resp:
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
    finally:
        await _delete_job(job_id)

    assert any(x.startswith("REPLAY:line one\nline two\n") for x in received_lines)
    assert "line three" in received_lines
    assert "DUP should drop" not in received_lines


@pytest.mark.asyncio
async def test_events_terminal_fallback_without_done_notify(authed_live_client):
    """Simulates a LogPublisher whose DB connection never came up (Task 4's
    defensive case): no `done` NOTIFY is ever sent, but the job's status row
    is updated to a terminal value directly. The endpoint must independently
    poll Job.status and close the stream once it goes terminal, instead of
    hanging forever waiting for a NOTIFY that will never arrive."""
    job_id = uuid.uuid4()
    await _insert_job(job_id, "running", "line one\n")

    async def _mark_completed_after_delay():
        await asyncio.sleep(0.5)
        await _set_status(job_id, "completed")

    marker = asyncio.create_task(_mark_completed_after_delay())
    try:
        async with authed_live_client.stream("GET", f"/jobs/{job_id}/events") as resp:
            assert resp.status_code == 200
            saw_done_status = None
            async for raw in resp.aiter_lines():
                if raw.startswith("data:"):
                    obj = json.loads(raw[len("data:"):].strip())
                    if obj.get("done"):
                        saw_done_status = obj.get("status")
                        break
            assert saw_done_status == "completed"
    finally:
        await marker
        await _delete_job(job_id)


@pytest.mark.asyncio
async def test_events_404_for_missing_job(authed_client):
    resp = await authed_client.get(f"/jobs/{uuid.uuid4()}/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_events_requires_auth(client):
    resp = await client.get(f"/jobs/{uuid.uuid4()}/events")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_events_disconnect_cleanup(db, monkeypatch):
    """Verify that a client disconnect (the ASGI server tearing down the
    generator early, which raises GeneratorExit at the current yield/await)
    properly cleans up the dedicated asyncpg connection: add_listener is
    called exactly once before any frame is yielded, and remove_listener +
    close are each called exactly once during teardown.

    This calls the route function directly, bypassing HTTP/ASGI entirely
    (ASGITransport fully buffers responses and can't observe partial
    streaming + early cancellation — see the NOTE at the top of this file),
    and fakes asyncpg.connect so the calls can be observed without a real
    LISTEN/NOTIFY connection.
    """
    import api.routes.jobs as jobs_module
    from api.models import Job

    job = Job(topic="t", tone="warm", word_count=100, status="running",
              logs="line one\n")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    calls: list[str] = []

    class FakeConn:
        async def add_listener(self, channel, callback):
            calls.append("add_listener")

        async def remove_listener(self, channel, callback):
            calls.append("remove_listener")

        async def close(self):
            calls.append("close")

        async def fetchrow(self, query, *args):
            calls.append("fetchrow")
            return {"logs": job.logs, "status": job.status}

        async def fetchval(self, query, *args):
            calls.append("fetchval")
            return job.status

    async def fake_connect(dsn):
        calls.append("connect")
        return FakeConn()

    monkeypatch.setattr(jobs_module.asyncpg, "connect", fake_connect)

    resp = await jobs_module.stream_job_events(job_id=job.id, db=db, _="user")

    # event_gen() is an async generator: nothing inside it runs until the
    # first __anext__() drives it, so no calls have happened yet.
    assert calls == []
    await resp.body_iterator.__anext__()  # replay frame
    # add_listener must happen before the replay (fetchrow) is read.
    assert calls.index("add_listener") < calls.index("fetchrow")
    assert calls.count("add_listener") == 1

    # Simulate the ASGI server tearing down the generator on client
    # disconnect: this raises GeneratorExit at the generator's current
    # await point (inside the live poll loop's asyncio.wait_for).
    await resp.body_iterator.aclose()

    assert calls.count("remove_listener") == 1
    assert calls.count("close") == 1
    assert calls.index("remove_listener") < calls.index("close")


@pytest.mark.asyncio
async def test_events_closes_on_already_terminal_job(authed_client, db):
    """If the job is already terminal when the client connects, the stream
    must emit `event: done` immediately without waiting on any NOTIFY. This
    doesn't require real concurrency (the generator returns on its own after
    one frame), so the ordinary buffering-but-in-process authed_client works
    fine here.

    The Job row is inserted via raw asyncpg (autocommit), not the `db`
    fixture, because the endpoint now reads its replay snapshot via a
    dedicated asyncpg connection opened *after* the listener subscribes
    (Finding 1/3 fix): that connection is a genuinely separate physical
    connection from the `db` fixture's transactional session, so it can
    only see rows that are actually committed to the database, not rows
    only visible inside `db`'s test transaction.
    """
    job_id = uuid.uuid4()
    await _insert_job(job_id, "completed", "done already\n")
    try:
        resp = await authed_client.get(f"/jobs/{job_id}/events")
        assert resp.status_code == 200
        saw_done = False
        for raw_line in resp.text.splitlines():
            if raw_line.startswith("event: done"):
                saw_done = True
            if raw_line.startswith("data:") and saw_done:
                obj = json.loads(raw_line[len("data:"):].strip())
                assert obj.get("done") is True
                assert obj.get("status") == "completed"
                break
        assert saw_done
    finally:
        await _delete_job(job_id)
