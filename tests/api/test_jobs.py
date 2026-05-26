import pytest
import pytest_asyncio
import uuid
from sqlalchemy import select
from api.auth import hash_password
from api.models import Settings, Job


@pytest_asyncio.fixture
async def seeded_settings(db):
    result = await db.execute(select(Settings))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    s = Settings(password_hash=hash_password("testpass"))
    db.add(s)
    await db.commit()
    return s


async def test_create_job(authed_client, seeded_settings):
    resp = await authed_client.post("/jobs", json={"topic": "AI in healthcare", "tone": "informative", "word_count": 3500})
    assert resp.status_code == 201
    data = resp.json()
    assert data["topic"] == "AI in healthcare"
    assert data["status"] == "pending"
    assert "id" in data


async def test_list_jobs(authed_client, seeded_settings):
    await authed_client.post("/jobs", json={"topic": "Topic A", "tone": "casual", "word_count": 2000})
    await authed_client.post("/jobs", json={"topic": "Topic B", "tone": "technical", "word_count": 4000})
    resp = await authed_client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) >= 2
    assert jobs[0]["created_at"] >= jobs[1]["created_at"]


async def test_get_job(authed_client, seeded_settings):
    create_resp = await authed_client.post("/jobs", json={"topic": "Get test", "tone": "informative", "word_count": 3500})
    job_id = create_resp.json()["id"]
    resp = await authed_client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


async def test_get_job_not_found(authed_client, seeded_settings):
    resp = await authed_client.get(f"/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_delete_pending_job(authed_client, seeded_settings):
    create_resp = await authed_client.post("/jobs", json={"topic": "Delete me", "tone": "informative", "word_count": 3500})
    job_id = create_resp.json()["id"]
    resp = await authed_client.delete(f"/jobs/{job_id}")
    assert resp.status_code == 204
    get_resp = await authed_client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 404


async def test_delete_non_pending_job_fails(authed_client, db, seeded_settings):
    job = Job(topic="Running job", tone="informative", word_count=3500, status="running")
    db.add(job)
    await db.commit()
    resp = await authed_client.delete(f"/jobs/{job.id}")
    assert resp.status_code == 409


async def test_retry_failed_job(authed_client, db, seeded_settings):
    job = Job(topic="Failed job", tone="informative", word_count=3500, status="failed", error="timeout")
    db.add(job)
    await db.commit()
    resp = await authed_client.post(f"/jobs/{job.id}/retry")
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["topic"] == "Failed job"


async def test_retry_non_failed_job_fails(authed_client, db, seeded_settings):
    job = Job(topic="Pending job", tone="informative", word_count=3500, status="pending")
    db.add(job)
    await db.commit()
    resp = await authed_client.post(f"/jobs/{job.id}/retry")
    assert resp.status_code == 409


async def test_unauthenticated_requests_rejected(client):
    resp = await client.get("/jobs")
    assert resp.status_code == 401
