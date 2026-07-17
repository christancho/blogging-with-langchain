import asyncio
import json
import os
import time
import uuid
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from api.db import get_db
from api.models import Job
from api.auth import require_auth
from api.pg_dsn import plain_dsn
from api.log_stream import channel_for, count_completed_lines

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TERMINAL_STATUSES = ("completed", "failed", "published")
_KEEPALIVE_SECONDS = 15
_POLL_SECONDS = 2


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
    from agentic.config import Config
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


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Return the captured log output for a job."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"logs": job.logs}


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Server-Sent Events stream of a job's live pipeline log.

    Replays Job.logs on connect, then forwards live NOTIFY events with seq > k
    (the number of newline-completed lines already covered by the replay).

    Independently of the `done` NOTIFY, the job's `status` column is polled
    periodically via the existing DB session: if the publisher's own DB
    connection never came up (see LogPublisher's defensive connect-failure
    handling), no `done` NOTIFY will ever be sent, and this fallback is what
    keeps the stream from hanging forever. Whichever signal (NOTIFY or poll)
    observes a terminal status first wins and closes the stream.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    replay = job.logs or ""
    k = count_completed_lines(replay)
    terminal_at_connect = job.status in _TERMINAL_STATUSES
    status_at_connect = job.status
    channel = channel_for(job_id)

    async def event_gen():
        conn = await asyncpg.connect(plain_dsn(os.environ["DATABASE_URL"]))
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_notify(_conn, _pid, _ch, payload):
            loop.call_soon_threadsafe(q.put_nowait, payload)

        try:
            # Subscribe FIRST so nothing published during setup is lost.
            await conn.add_listener(channel, on_notify)
            try:
                # Replay snapshot (up to 2s stale), then live with seq > k.
                yield f"data: {json.dumps({'replay': replay})}\n\n"
                if terminal_at_connect:
                    yield f"event: done\ndata: {json.dumps({'done': True, 'status': status_at_connect})}\n\n"
                    return

                last_keepalive = time.monotonic()
                while True:
                    try:
                        payload = await asyncio.wait_for(q.get(), timeout=_POLL_SECONDS)
                    except asyncio.TimeoutError:
                        # No NOTIFY arrived within the poll window. Independently
                        # check whether the job has already gone terminal (e.g.
                        # the publisher's connection never came up, so `done`
                        # will never be NOTIFYd) before deciding whether to send
                        # a keep-alive comment and keep waiting.
                        result = await db.execute(select(Job.status).where(Job.id == job_id))
                        current_status = result.scalar_one_or_none()
                        if current_status in _TERMINAL_STATUSES:
                            yield f"event: done\ndata: {json.dumps({'done': True, 'status': current_status})}\n\n"
                            return

                        now = time.monotonic()
                        if now - last_keepalive >= _KEEPALIVE_SECONDS:
                            yield ": keep-alive\n\n"
                            last_keepalive = now
                        continue

                    obj = json.loads(payload)
                    if obj.get("done"):
                        yield f"event: done\ndata: {payload}\n\n"
                        return
                    if obj.get("seq", 0) > k:
                        yield f"data: {payload}\n\n"
            finally:
                await conn.remove_listener(channel, on_notify)
        finally:
            await conn.close()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: str = Depends(require_auth)):
    """Remove a job from the queue. Running jobs are deleted immediately; the worker stops at the next node boundary."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
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

    from agentic.nodes.publisher import publisher_node
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
