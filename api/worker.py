import asyncio
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

logger = logging.getLogger(__name__)


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
    from sqlalchemy import select
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
    from api.models import Job

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

    try:
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

            async with session_factory() as db:
                job = await db.get(Job, job_id)
                job.current_node = node_name
                await db.commit()

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
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            job.status = "failed"
            job.error = str(e)
            job.current_node = None
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
