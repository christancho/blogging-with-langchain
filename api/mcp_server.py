import uuid

from sqlalchemy import select, desc

from api.models import Job, Settings


def _curate_result(result: dict | None) -> dict | None:
    """Trim the stored pipeline state to the fields worth showing in Claude."""
    if not result:
        return None
    return {
        "final_content": result.get("final_content", ""),
        "seo_title": result.get("seo_title", result.get("article_title", "")),
        "seo_description": result.get("seo_description", ""),
        "tags": result.get("tags", []),
        "word_count": result.get("word_count"),
        "warnings": result.get("warnings", []),
        "ghost_post_url": result.get("ghost_post_url"),
    }


def _serialize_job(job: Job, include_result: bool = False) -> dict:
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
    from agentic.config import Config
    async with session_factory() as db:
        settings = (await db.execute(select(Settings))).scalar_one_or_none()
        default_tone = settings.default_tone if settings else Config.BLOG_TONE
        default_wc = settings.default_word_count if settings else Config.WORD_COUNT_TARGET
        job = Job(
            topic=topic,
            tone=tone or default_tone,
            word_count=word_count or default_wc,
            instructions=instructions,
            status="pending",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return {"job_id": str(job.id), "status": job.status}


async def get_job_impl(session_factory, job_id) -> dict:
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(str(job_id)))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        return _serialize_job(job, include_result=True)


async def list_jobs_impl(session_factory, limit: int = 20) -> list[dict]:
    async with session_factory() as db:
        rows = await db.execute(select(Job).order_by(desc(Job.created_at)).limit(limit))
        return [_serialize_job(j) for j in rows.scalars().all()]


async def get_job_logs_impl(session_factory, job_id) -> dict:
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(str(job_id)))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        return {"logs": job.logs or ""}
