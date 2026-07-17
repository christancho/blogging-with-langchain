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


@pytest.mark.asyncio
async def test_publish_survives_unreachable_db():
    import uuid
    from api.log_stream import LogPublisher
    pub = LogPublisher(uuid.uuid4(), "postgresql://bad:bad@127.0.0.1:1/nope")
    pub.start()
    pub.publish(1, "line while db down")  # must not raise
    pub.stop("failed")                    # must return, not hang
    assert pub._thread is not None and not pub._thread.is_alive()
