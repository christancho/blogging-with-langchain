import asyncio
import io
import logging
import os
import sys
import threading
from datetime import datetime, timezone

# Ensure the repo root is on sys.path so graph.py can be imported
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agentic.graph import create_blog_graph  # noqa: E402 — must come after sys.path setup
from agentic.config import Config  # noqa: E402 — must come after sys.path setup
from sqlalchemy import select  # noqa: E402 — must come after sys.path setup

logger = logging.getLogger(__name__)


class TeeWriter:
    """Writes to both real stdout and an internal buffer for pipeline log capture."""

    def __init__(self, real_stdout):
        self._real = real_stdout
        self._buf = io.StringIO()

    def write(self, text: str) -> int:
        self._real.write(text)
        self._buf.write(text)
        return len(text)

    def flush(self) -> None:
        self._real.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue()

    def clear(self) -> None:
        self._buf.truncate(0)
        self._buf.seek(0)

    def __getattr__(self, name: str):
        return getattr(self._real, name)


def start_worker() -> threading.Thread:
    """Start the background worker as a daemon thread.

    Returns:
        The started daemon thread running the worker loop.
    """
    t = threading.Thread(target=_worker_thread, daemon=True, name="blog-worker")
    t.start()
    logger.info("Background worker thread started")
    return t


def _worker_thread() -> None:
    """Entry point for the worker daemon thread; runs the async loop."""
    asyncio.run(_worker_loop())


async def _worker_loop() -> None:
    """Poll for pending jobs every 5 seconds and execute them."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from api.models import Job

    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    while True:
        try:
            async with session_factory() as db:
                result = await db.execute(
                    select(Job)
                    .where(Job.status == "pending")
                    .order_by(Job.created_at)
                    .limit(1)
                )
                job = result.scalar_one_or_none()

            if job:
                await _run_job(job.id, session_factory)
            else:
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Worker loop error: {e}", exc_info=True)
            await asyncio.sleep(5)


async def _run_job(job_id, session_factory) -> None:
    """Execute one LangGraph job, updating DB state at each step.

    Args:
        job_id: UUID of the Job row to execute.
        session_factory: SQLAlchemy async_sessionmaker used to open DB sessions.
    """
    from api.models import Job, Settings

    try:
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            if not job:
                logger.error(f"Job {job_id} not found in DB, skipping")
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            await db.commit()
            topic = job.topic
            tone = job.tone
            word_count = job.word_count
            instructions = job.instructions or ""

            settings_result = await db.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            if settings:
                Config.OPENROUTER_TEMPERATURE = settings.llm_temperature
                Config.OPENROUTER_MODEL = settings.llm_model
                # Safe: worker processes one job at a time; concurrent jobs would need a lock here
                logger.info(f"LLM settings from DB: model={settings.llm_model}, temperature={settings.llm_temperature}")
    except Exception as e:
        logger.error(f"Job {job_id} failed to start: {e}", exc_info=True)
        try:
            async with session_factory() as db:
                job = await db.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            logger.error(f"Could not mark job {job_id} as failed after startup error")
        return

    tee = None
    try:
        tee = TeeWriter(sys.stdout)
        sys.stdout = tee
        graph = create_blog_graph()
        initial_state = {
            "topic": topic,
            "tone": tone,
            "word_count_target": word_count,
            "instructions": instructions,
        }
        accumulated: dict = dict(initial_state)

        for chunk in graph.stream(initial_state):
            node_name = next(iter(chunk))
            accumulated.update(chunk[node_name])

            new_output = tee.getvalue()
            tee.clear()
            async with session_factory() as db:
                job = await db.get(Job, job_id)
                job.current_node = node_name
                if new_output:
                    job.logs = (job.logs or "") + new_output
                await db.commit()

        if Config.is_langsmith_enabled():
            try:
                from agentic.tools import get_latest_run_cost, format_langsmith_cost_report
                cost_info = get_latest_run_cost(Config.LANGCHAIN_PROJECT)
                if cost_info:
                    print(format_langsmith_cost_report(cost_info))
            except Exception as cost_err:
                print(f"⚠️  Could not fetch cost data: {cost_err}")

        async with session_factory() as db:
            job = await db.get(Job, job_id)
            job.status = "completed"
            job.result = accumulated
            job.current_node = None
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        remaining = tee.getvalue() if tee is not None else ""
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            job.status = "failed"
            job.error = str(e)
            job.current_node = None
            job.completed_at = datetime.now(timezone.utc)
            if remaining:
                job.logs = (job.logs or "") + remaining
            await db.commit()
    finally:
        if tee is not None:
            sys.stdout = tee._real
