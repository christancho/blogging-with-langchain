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
