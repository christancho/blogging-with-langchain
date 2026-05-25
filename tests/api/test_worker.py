import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from api.models import Job, Settings
from api.auth import hash_password


@pytest_asyncio.fixture
async def seeded_settings(db):
    s = Settings(password_hash=hash_password("testpass"))
    db.add(s)
    await db.commit()
    return s


def make_session_factory(db: AsyncSession):
    """Return a session factory that always yields the same session.

    This allows _run_job (which opens its own sessions) to share the test
    transaction so it can see rows written by the test's ``db`` session.
    """
    @asynccontextmanager
    async def _factory():
        yield db

    class _FakeSessionmaker:
        def __call__(self):
            return _factory()

    return _FakeSessionmaker()


async def test_run_job_sets_running_then_completed(db, seeded_settings):
    """Worker marks job running then completed with result."""
    job = Job(topic="LangChain guide", tone="informative", word_count=3500, status="pending")
    db.add(job)
    await db.flush()

    fake_state = {"article_content": "Full article here", "seo_title": "LangChain Guide", "approval_status": "approved"}

    mock_graph = MagicMock()
    mock_graph.stream.return_value = iter([{"writer": fake_state}])

    with patch("api.worker.create_blog_graph", return_value=mock_graph):
        from api.worker import _run_job
        session_factory = make_session_factory(db)
        await _run_job(job.id, session_factory)

    await db.refresh(job)
    assert job.status == "completed"
    assert job.result is not None
    assert job.completed_at is not None
    assert job.error is None


async def test_run_job_sets_failed_on_exception(db, seeded_settings):
    """Worker catches exceptions and marks job failed."""
    job = Job(topic="Failing topic", tone="informative", word_count=3500, status="pending")
    db.add(job)
    await db.flush()

    mock_graph = MagicMock()
    mock_graph.stream.side_effect = RuntimeError("API timeout")

    with patch("api.worker.create_blog_graph", return_value=mock_graph):
        from api.worker import _run_job
        session_factory = make_session_factory(db)
        await _run_job(job.id, session_factory)

    await db.refresh(job)
    assert job.status == "failed"
    assert "API timeout" in job.error
    assert job.completed_at is not None


async def test_run_job_updates_current_node(db, seeded_settings):
    """Worker writes current_node to DB after each LangGraph step."""
    job = Job(topic="Multi-step topic", tone="informative", word_count=3500, status="pending")
    db.add(job)
    await db.flush()

    mock_graph = MagicMock()
    mock_graph.stream.return_value = iter([
        {"research": {"research_summary": "Research done"}},
        {"writer": {"article_content": "Article written"}},
    ])

    with patch("api.worker.create_blog_graph", return_value=mock_graph):
        from api.worker import _run_job
        session_factory = make_session_factory(db)
        await _run_job(job.id, session_factory)

    await db.refresh(job)
    assert job.current_node is None  # cleared after completion
    assert job.status == "completed"
