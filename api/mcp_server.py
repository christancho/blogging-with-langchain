import uuid

from mcp.server.fastmcp import FastMCP
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


async def publish_blog_impl(session_factory, job_id) -> dict:
    """Publish a completed job's article to Ghost CMS.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        job_id: The job's UUID (as a string or UUID instance).

    Returns:
        A dict with the published post's "url" and "post_id" (as returned
        by publisher_node's state updates).

    Raises:
        ValueError: If no job exists with the given id, the job is not in
            "completed" status, the job has no result to publish, or the
            Ghost publish itself fails (message is the last recorded error).
    """
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(str(job_id)))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        if job.status != "completed":
            raise ValueError("Only completed jobs can be published")
        if not job.result:
            raise ValueError("Job has no result to publish")

        from agentic.nodes.publisher import publisher_node
        state_updates = publisher_node(job.result)

        if state_updates.get("publication_status") == "failed":
            errors = state_updates.get("errors", ["Ghost publish failed"])
            raise ValueError(errors[-1])

        job.status = "published"
        job.result = {**job.result, **state_updates}
        await db.commit()
        return {
            "url": state_updates.get("ghost_post_url"),
            "post_id": state_updates.get("ghost_post_id"),
        }


async def retry_blog_impl(session_factory, job_id) -> dict:
    """Re-queue a failed job as a new pending job.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        job_id: The failed job's UUID (as a string or UUID instance).

    Returns:
        A dict with the new job's "job_id" and initial "status" ("pending").

    Raises:
        ValueError: If no job exists with the given id, or the job is not
            in "failed" status.
    """
    async with session_factory() as db:
        original = await db.get(Job, uuid.UUID(str(job_id)))
        if not original:
            raise ValueError(f"Job not found: {job_id}")
        if original.status != "failed":
            raise ValueError("Only failed jobs can be retried")
        new_job = Job(
            topic=original.topic,
            tone=original.tone,
            word_count=original.word_count,
            instructions=original.instructions,
            status="pending",
        )
        db.add(new_job)
        await db.commit()
        await db.refresh(new_job)
        return {"job_id": str(new_job.id), "status": new_job.status}


def _settings_dict(s: Settings) -> dict:
    """Convert a Settings ORM instance to a dict, excluding sensitive fields.

    Args:
        s: The Settings ORM instance to convert.

    Returns:
        A dict with all public Settings fields (default_tone, default_word_count,
        llm_temperature, llm_model, auto_publish_to_ghost), excluding
        password_hash and other sensitive data.
    """
    return {
        "default_tone": s.default_tone,
        "default_word_count": s.default_word_count,
        "llm_temperature": s.llm_temperature,
        "llm_model": s.llm_model,
        "auto_publish_to_ghost": s.auto_publish_to_ghost,
    }


async def get_settings_impl(session_factory) -> dict:
    """Fetch the application settings.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.

    Returns:
        A dict with all public Settings fields (default_tone, default_word_count,
        llm_temperature, llm_model, auto_publish_to_ghost).
    """
    async with session_factory() as db:
        s = (await db.execute(select(Settings))).scalar_one()
        return _settings_dict(s)


async def update_settings_impl(
    session_factory,
    default_tone=None,
    default_word_count=None,
    llm_temperature=None,
    llm_model=None,
    auto_publish_to_ghost=None,
) -> dict:
    """Update application settings with partial changes.

    Only fields that are not None are updated. All other fields remain unchanged.

    Args:
        session_factory: An async_sessionmaker (or compatible factory) used
            to open a database session.
        default_tone: Optional new default tone for blog generation.
        default_word_count: Optional new default target word count.
        llm_temperature: Optional new LLM temperature setting.
        llm_model: Optional new LLM model name.
        auto_publish_to_ghost: Optional new auto-publish setting.

    Returns:
        A dict with all public Settings fields after the update.
    """
    async with session_factory() as db:
        s = (await db.execute(select(Settings))).scalar_one()
        if default_tone is not None:
            s.default_tone = default_tone
        if default_word_count is not None:
            s.default_word_count = default_word_count
        if llm_temperature is not None:
            s.llm_temperature = llm_temperature
        if llm_model is not None:
            s.llm_model = llm_model
        if auto_publish_to_ghost is not None:
            s.auto_publish_to_ghost = auto_publish_to_ghost
        await db.commit()
        await db.refresh(s)
        return _settings_dict(s)


def build_mcp(session_factory, token_verifier=None, auth_settings=None) -> "FastMCP":
    """Build the BlogForge MCP server. Tools bind to the given session factory.

    When both token_verifier and auth_settings are provided, all tools require a
    valid bearer token; otherwise the server runs unauthenticated (tests only).
    """
    kwargs = {"name": "BlogForge", "streamable_http_path": "/mcp"}
    if token_verifier is not None and auth_settings is not None:
        kwargs["token_verifier"] = token_verifier
        kwargs["auth"] = auth_settings
    mcp = FastMCP(**kwargs)

    @mcp.tool()
    async def generate_blog(
        topic: str,
        tone: str | None = None,
        word_count: int | None = None,
        instructions: str | None = None,
    ) -> dict:
        """Queue a new blog-generation job. Returns a job_id to poll with get_job."""
        return await generate_blog_impl(session_factory, topic, tone, word_count, instructions)

    @mcp.tool()
    async def get_job(job_id: str) -> dict:
        """Get a job's status and, once completed, the finished article for review."""
        return await get_job_impl(session_factory, job_id)

    @mcp.tool()
    async def list_jobs(limit: int = 20) -> list[dict]:
        """List recent blog jobs, newest first."""
        return await list_jobs_impl(session_factory, limit)

    @mcp.tool()
    async def get_job_logs(job_id: str) -> dict:
        """Get the captured pipeline log output for a job."""
        return await get_job_logs_impl(session_factory, job_id)

    @mcp.tool()
    async def publish_blog(job_id: str) -> dict:
        """Publish a completed job's article to Ghost CMS."""
        return await publish_blog_impl(session_factory, job_id)

    @mcp.tool()
    async def retry_blog(job_id: str) -> dict:
        """Re-queue a failed job as a new pending job."""
        return await retry_blog_impl(session_factory, job_id)

    @mcp.tool()
    async def get_settings() -> dict:
        """Get current generation defaults and settings."""
        return await get_settings_impl(session_factory)

    @mcp.tool()
    async def update_settings(
        default_tone: str | None = None,
        default_word_count: int | None = None,
        llm_temperature: float | None = None,
        llm_model: str | None = None,
        auto_publish_to_ghost: bool | None = None,
    ) -> dict:
        """Update one or more generation settings."""
        return await update_settings_impl(
            session_factory,
            default_tone,
            default_word_count,
            llm_temperature,
            llm_model,
            auto_publish_to_ghost,
        )

    return mcp
