import uuid

from sqlalchemy import select, desc

from api.models import Job, Settings


def _curate_result(result: dict | None) -> dict | None:
    """Trim the stored pipeline state to the fields worth showing in Claude.

    Args:
        result: The raw pipeline state dict stored on a Job, or None.

    Returns:
        A dict with only the fields relevant to a consumer of the MCP tools
        (content, SEO metadata, tags, computed word count, warnings, and the
        published Ghost URL), or None if no result is available. Word count
        is computed from the article text since the state has no dedicated
        word-count field.
    """
    if not result:
        return None
    final_content = result.get("final_content", "")
    return {
        "final_content": final_content,
        "seo_title": result.get("seo_title", result.get("article_title", "")),
        "meta_description": result.get("meta_description", ""),
        "tags": result.get("tags", []),
        "word_count": len(final_content.split()) if final_content else 0,
        "warnings": result.get("warnings", []),
        "ghost_post_url": result.get("ghost_post_url"),
    }


def _serialize_job(job: Job, include_result: bool = False) -> dict:
    """Build the API-facing representation of a Job row.

    Args:
        job: The Job ORM instance to serialize.
        include_result: If True, include a curated view of the job's stored
            pipeline result under the "result" key.

    Returns:
        A dict with job metadata (id, topic, status, current_node,
        timestamps, error) and, optionally, the curated result.
    """
    d = {
        "id": str(job.id),
        "topic": job.topic,
        "status": job.status,
        "current_node": job.current_node,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
    }
    if include_result:
        d["result"] = _curate_result(job.result)
    return d


async def generate_blog_impl(
    session_factory, topic, tone=None, word_count=None, instructions=None
) -> dict:
    """Create a new pending blog generation job.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        topic: The blog topic to generate content for.
        tone: Explicit tone override. If None, falls back to the Settings
            row's default_tone, then Config.BLOG_TONE.
        word_count: Explicit target word count override. If None, falls
            back to the Settings row's default_word_count, then
            Config.WORD_COUNT_TARGET.
        instructions: Optional free-form instructions for the writer.

    Returns:
        A dict with the new job's "job_id" and initial "status".
    """
    from agentic.config import Config
    async with session_factory() as db:
        settings = (await db.execute(select(Settings))).scalar_one_or_none()
        default_tone = settings.default_tone if settings else Config.BLOG_TONE
        default_wc = settings.default_word_count if settings else Config.WORD_COUNT_TARGET
        job = Job(
            topic=topic,
            tone=tone if tone is not None else default_tone,
            word_count=word_count if word_count is not None else default_wc,
            instructions=instructions,
            status="pending",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return {"job_id": str(job.id), "status": job.status}


async def get_job_impl(session_factory, job_id) -> dict:
    """Fetch a single job with its curated result.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        job_id: The job's UUID (as a string or UUID instance).

    Returns:
        The serialized job dict, including a curated "result" field.

    Raises:
        ValueError: If no job exists with the given id.
    """
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(str(job_id)))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        return _serialize_job(job, include_result=True)


async def list_jobs_impl(session_factory, limit: int = 20) -> list[dict]:
    """List recent jobs, newest first.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        limit: Maximum number of jobs to return.

    Returns:
        A list of serialized job dicts (without the curated result, which
        is only included by get_job_impl).
    """
    async with session_factory() as db:
        rows = await db.execute(select(Job).order_by(desc(Job.created_at)).limit(limit))
        return [_serialize_job(j) for j in rows.scalars().all()]


async def get_job_logs_impl(session_factory, job_id) -> dict:
    """Fetch the accumulated log output for a job.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        job_id: The job's UUID (as a string or UUID instance).

    Returns:
        A dict with the job's "logs" as a single string (empty if none).

    Raises:
        ValueError: If no job exists with the given id.
    """
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(str(job_id)))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        return {"logs": job.logs or ""}
