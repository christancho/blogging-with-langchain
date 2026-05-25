import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from api.db import get_db
from api.models import Job
from api.auth import require_auth

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreate(BaseModel):
    topic: str
    tone: str | None = None
    word_count: int | None = None
    instructions: str | None = None


def _serialize(job: Job, include_result: bool = False) -> dict:
    d = {
        "id": str(job.id),
        "topic": job.topic,
        "tone": job.tone,
        "word_count": job.word_count,
        "instructions": job.instructions,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "current_node": job.current_node,
        "error": job.error,
    }
    if include_result:
        d["result"] = job.result
    return d


@router.get("")
async def list_jobs(db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """List all jobs ordered newest first."""
    result = await db.execute(select(Job).order_by(desc(Job.created_at)))
    return [_serialize(j) for j in result.scalars().all()]


@router.post("", status_code=201)
async def create_job(body: JobCreate, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Add a new job to the queue as pending."""
    from config import Config
    job = Job(
        topic=body.topic,
        tone=body.tone or Config.BLOG_TONE,
        word_count=body.word_count or Config.WORD_COUNT_TARGET,
        instructions=body.instructions,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _serialize(job)


@router.get("/{job_id}")
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Get a single job including its result JSONB."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize(job, include_result=True)


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Remove a pending job from the queue."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending jobs can be deleted")
    await db.delete(job)
    await db.commit()


@router.post("/{job_id}/publish")
async def publish_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Publish a completed job to Ghost CMS."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed jobs can be published")
    if not job.result:
        raise HTTPException(status_code=409, detail="Job has no result to publish")

    from nodes.publisher import publisher_node
    state_updates = publisher_node(job.result)

    if state_updates.get("publication_status") == "failed":
        raise HTTPException(status_code=502, detail=state_updates.get("errors", ["Ghost publish failed"])[-1])

    job.status = "published"
    job.result = {**job.result, **state_updates}
    await db.commit()
    return {"url": state_updates.get("ghost_post_url"), "post_id": state_updates.get("ghost_post_id")}


@router.post("/{job_id}/retry", status_code=201)
async def retry_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Re-queue a failed job as a new pending job."""
    original = await db.get(Job, job_id)
    if not original:
        raise HTTPException(status_code=404, detail="Job not found")
    if original.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried")

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
    return _serialize(new_job)
