import asyncio
import json
import os
import uuid
import asyncpg
from api.pg_dsn import plain_dsn

DSN = plain_dsn(os.environ["DATABASE_URL"])

# Like the live tests in test_jobs_events.py, these run against the real app in
# a uvicorn subprocess (`authed_live_client`), because httpx's ASGITransport
# buffers the whole response and cannot observe a stream while it is open.
# Job rows are written with autocommitted asyncpg calls so the Postgres trigger
# fires exactly as it does for the worker, REST routes, and MCP tools.


async def _exec(sql: str, *args) -> None:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _insert_job(job_id: uuid.UUID, status: str) -> None:
    await _exec(
        "INSERT INTO jobs (id, topic, tone, word_count, status) VALUES ($1, $2, 'warm', 100, $3)",
        job_id, f"topic {job_id}", status,
    )


class _Snapshots:
    """Collects the `jobs` events of an open /jobs/stream response."""

    def __init__(self, resp):
        self.items: list[list[dict]] = []
        self._resp = resp
        self._task = asyncio.create_task(self._pump())

    async def _pump(self):
        event = None
        async for raw in self._resp.aiter_lines():
            if raw.startswith("event:"):
                event = raw[len("event:"):].strip()
            elif raw.startswith("data:") and event == "jobs":
                self.items.append(json.loads(raw[len("data:"):].strip()))
            elif raw == "":
                event = None

    async def wait_for(self, predicate, timeout: float = 5.0) -> list[dict]:
        """Wait until the latest snapshot satisfies predicate; return it."""
        async def poll():
            while not (self.items and predicate(self.items[-1])):
                await asyncio.sleep(0.05)
            return self.items[-1]
        return await asyncio.wait_for(poll(), timeout)

    def stop(self):
        self._task.cancel()


def _ids(snapshot: list[dict]) -> set[str]:
    return {j["id"] for j in snapshot}


async def test_stream_requires_auth(client):
    resp = await client.get("/jobs/stream")
    assert resp.status_code == 401


async def test_stream_sends_active_jobs_on_connect(authed_live_client):
    pending, done = uuid.uuid4(), uuid.uuid4()
    await _insert_job(pending, "pending")
    await _insert_job(done, "completed")
    try:
        async with authed_live_client.stream("GET", "/jobs/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            snaps = _Snapshots(resp)
            try:
                first = await snaps.wait_for(lambda s: True)
            finally:
                snaps.stop()
    finally:
        await _exec("DELETE FROM jobs WHERE id = ANY($1)", [pending, done])

    assert _ids(first) == {str(pending)}
    job = first[0]
    assert job["status"] == "pending"
    assert job["topic"] == f"topic {pending}"
    assert "logs" not in job and "result" not in job


async def test_stream_pushes_job_lifecycle(authed_live_client):
    job_id = uuid.uuid4()
    jid = str(job_id)
    try:
        async with authed_live_client.stream("GET", "/jobs/stream") as resp:
            snaps = _Snapshots(resp)
            try:
                await snaps.wait_for(lambda s: jid not in _ids(s))

                await _insert_job(job_id, "pending")
                await snaps.wait_for(lambda s: jid in _ids(s))

                await _exec("UPDATE jobs SET status = 'running' WHERE id = $1", job_id)
                await snaps.wait_for(lambda s: any(j["id"] == jid and j["status"] == "running" for j in s))

                await _exec("UPDATE jobs SET current_node = 'writer' WHERE id = $1", job_id)
                await snaps.wait_for(lambda s: any(j["id"] == jid and j["current_node"] == "writer" for j in s))

                # A finished job leaves the active set.
                await _exec("UPDATE jobs SET status = 'completed' WHERE id = $1", job_id)
                await snaps.wait_for(lambda s: jid not in _ids(s))

                # Re-queue then delete: a delete also pushes.
                await _exec("UPDATE jobs SET status = 'pending' WHERE id = $1", job_id)
                await snaps.wait_for(lambda s: jid in _ids(s))
                await _exec("DELETE FROM jobs WHERE id = $1", job_id)
                await snaps.wait_for(lambda s: jid not in _ids(s))
            finally:
                snaps.stop()
    finally:
        await _exec("DELETE FROM jobs WHERE id = $1", job_id)


async def test_stream_ignores_log_only_updates(authed_live_client):
    """The worker flushes Job.logs every 2s; those writes must not push snapshots."""
    job_id = uuid.uuid4()
    await _insert_job(job_id, "running")
    try:
        async with authed_live_client.stream("GET", "/jobs/stream") as resp:
            snaps = _Snapshots(resp)
            try:
                await snaps.wait_for(lambda s: str(job_id) in _ids(s))
                before = len(snaps.items)
                for i in range(3):
                    await _exec("UPDATE jobs SET logs = COALESCE(logs, '') || $1 WHERE id = $2", f"line {i}\n", job_id)
                await asyncio.sleep(0.5)
                assert len(snaps.items) == before
            finally:
                snaps.stop()
    finally:
        await _exec("DELETE FROM jobs WHERE id = $1", job_id)
