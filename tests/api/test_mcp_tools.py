import json
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select

from api.models import Job, Settings
from api.auth import hash_password
from api.mcp_server import (
    generate_blog_impl,
    get_job_impl,
    list_jobs_impl,
    get_job_logs_impl,
)


@pytest_asyncio.fixture
async def session_factory(test_engine):
    """A real async_sessionmaker bound to the test engine.

    MCP tools open their own sessions (no FastAPI DI), so tests give them a
    factory on the test engine. The function-scoped test_engine drops all
    tables afterward, cleaning up committed rows.
    """
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_settings(session_factory):
    async with session_factory() as db:
        existing = (await db.execute(select(Settings))).scalar_one_or_none()
        if existing is None:
            db.add(Settings(password_hash=hash_password("testpass")))
            await db.commit()


async def test_generate_blog_inserts_pending(session_factory, seeded_settings):
    out = await generate_blog_impl(session_factory, topic="AI in healthcare")
    assert out["status"] == "pending"
    assert uuid.UUID(out["job_id"])  # parses as a UUID
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.topic == "AI in healthcare"
        assert job.status == "pending"


async def test_generate_blog_uses_settings_defaults(session_factory, seeded_settings):
    # Seed values that DIVERGE from Config.BLOG_TONE / Config.WORD_COUNT_TARGET so
    # this test can actually distinguish "read from the Settings row" from
    # "fell through to the Config default" (the two happen to share values
    # in seeded_settings's plain default row).
    async with session_factory() as db:
        settings = (await db.execute(select(Settings))).scalar_one()
        settings.default_tone = "editorial voice"
        settings.default_word_count = 2000
        await db.commit()

    out = await generate_blog_impl(session_factory, topic="Defaults test")
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.tone == "editorial voice"
        assert job.word_count == 2000


async def test_generate_blog_explicit_args_win(session_factory, seeded_settings):
    out = await generate_blog_impl(
        session_factory, topic="X", tone="casual", word_count=1200, instructions="be brief"
    )
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.tone == "casual"
        assert job.word_count == 1200
        assert job.instructions == "be brief"


async def test_get_job_returns_curated_result(session_factory, seeded_settings):
    final_content = "# Title\n\nBody text here"
    expected_word_count = len(final_content.split())
    async with session_factory() as db:
        job = Job(
            topic="Done", tone="informative", word_count=3500, status="completed",
            result={
                "final_content": final_content,
                "seo_title": "SEO Title",
                "meta_description": "desc",
                "tags": ["ai", "health"],
                "warnings": ["force_published"],
                "secret_internal_field": "should not leak",
            },
        )
        db.add(job)
        await db.commit()
        job_id = str(job.id)

    out = await get_job_impl(session_factory, job_id)
    assert out["status"] == "completed"
    assert out["result"]["final_content"] == final_content
    assert out["result"]["seo_title"] == "SEO Title"
    assert out["result"]["meta_description"] == "desc"
    assert out["result"]["tags"] == ["ai", "health"]
    assert out["result"]["word_count"] == expected_word_count
    assert out["result"]["warnings"] == ["force_published"]
    assert "secret_internal_field" not in out["result"]


async def test_get_job_not_found_raises(session_factory, seeded_settings):
    with pytest.raises(ValueError, match="Job not found"):
        await get_job_impl(session_factory, str(uuid.uuid4()))


async def test_list_jobs_newest_first(session_factory, seeded_settings):
    await generate_blog_impl(session_factory, topic="First")
    await generate_blog_impl(session_factory, topic="Second")
    jobs = await list_jobs_impl(session_factory, limit=10)
    assert len(jobs) >= 2
    assert jobs[0]["created_at"] >= jobs[1]["created_at"]
    assert "result" not in jobs[0]  # list is lightweight, no curated result


async def test_get_job_logs(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="L", tone="t", word_count=100, status="running", logs="line1\nline2\n")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    out = await get_job_logs_impl(session_factory, job_id)
    assert out["logs"] == "line1\nline2\n"


from api.mcp_server import publish_blog_impl, retry_blog_impl


async def test_publish_non_completed_rejected(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="P", tone="t", word_count=100, status="pending")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    with pytest.raises(ValueError, match="Only completed jobs can be published"):
        await publish_blog_impl(session_factory, job_id)


async def test_publish_completed_calls_publisher(session_factory, seeded_settings, monkeypatch):
    async with session_factory() as db:
        job = Job(
            topic="P", tone="t", word_count=100, status="completed",
            result={"final_content": "# T\n\nB", "seo_title": "T"},
        )
        db.add(job)
        await db.commit()
        job_id = str(job.id)

    def fake_publisher(state):
        return {
            "publication_status": "published",
            "ghost_post_url": "https://ghost.test/p/1",
            "ghost_post_id": "abc123",
        }
    monkeypatch.setattr("agentic.nodes.publisher.publisher_node", fake_publisher)

    out = await publish_blog_impl(session_factory, job_id)
    assert out["url"] == "https://ghost.test/p/1"
    assert out["post_id"] == "abc123"
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(job_id))
        assert job.status == "published"


async def test_publish_surfaces_ghost_failure(session_factory, seeded_settings, monkeypatch):
    async with session_factory() as db:
        job = Job(
            topic="P", tone="t", word_count=100, status="completed",
            result={"final_content": "# T"},
        )
        db.add(job)
        await db.commit()
        job_id = str(job.id)

    def fake_publisher(state):
        return {"publication_status": "failed", "errors": ["Ghost 401 Unauthorized"]}
    monkeypatch.setattr("agentic.nodes.publisher.publisher_node", fake_publisher)

    with pytest.raises(ValueError, match="Ghost 401 Unauthorized"):
        await publish_blog_impl(session_factory, job_id)


async def test_retry_failed_job(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="Failed", tone="t", word_count=100, status="failed", error="boom")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    out = await retry_blog_impl(session_factory, job_id)
    assert out["status"] == "pending"
    async with session_factory() as db:
        new_job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert new_job.topic == "Failed"
        assert new_job.id != uuid.UUID(job_id)


async def test_retry_non_failed_rejected(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="Pending", tone="t", word_count=100, status="pending")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    with pytest.raises(ValueError, match="Only failed jobs can be retried"):
        await retry_blog_impl(session_factory, job_id)


from api.mcp_server import get_settings_impl, update_settings_impl


async def test_get_settings(session_factory, seeded_settings):
    out = await get_settings_impl(session_factory)
    assert out["default_tone"] == "informative and insightful"
    assert out["default_word_count"] == 3500
    assert "password_hash" not in out


async def test_update_settings_partial(session_factory, seeded_settings):
    out = await update_settings_impl(session_factory, default_tone="snarky", auto_publish_to_ghost=False)
    assert out["default_tone"] == "snarky"
    assert out["auto_publish_to_ghost"] is False
    assert out["default_word_count"] == 3500  # untouched field unchanged


from mcp.shared.memory import create_connected_server_and_client_session
from api.mcp_server import build_mcp


async def test_tools_listed_and_callable_in_memory(session_factory, seeded_settings):
    mcp = build_mcp(session_factory)  # no auth for the in-memory client

    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        await client.initialize()

        tools = {t.name for t in (await client.list_tools()).tools}
        assert {
            "generate_blog", "get_job", "list_jobs", "get_job_logs",
            "publish_blog", "retry_blog", "get_settings", "update_settings",
        } <= tools

        # NOTE: the tool wrappers are annotated `-> dict` (unparameterized), which
        # FastMCP's func_metadata cannot turn into an output schema (bare `dict`
        # has no type hints to build a Pydantic model from), so `structuredContent`
        # is None. The payload is still available as JSON text in `content[0]`.
        created = await client.call_tool("generate_blog", {"topic": "End to end"})
        assert created.isError is False
        assert created.structuredContent is None
        job_id = json.loads(created.content[0].text)["job_id"]

        fetched = await client.call_tool("get_job", {"job_id": job_id})
        assert fetched.isError is False
        assert json.loads(fetched.content[0].text)["status"] == "pending"

        missing = await client.call_tool("get_job", {"job_id": str(uuid.uuid4())})
        assert missing.isError is True  # ValueError becomes a tool error
