import pytest
import uuid
from sqlalchemy import text


@pytest.mark.asyncio(loop_scope="function")
async def test_db_connection(db):
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_settings_model_insert(db):
    from api.models import Job, Settings
    from api.auth import hash_password
    s = Settings(password_hash=hash_password("secret"), default_tone="technical", default_word_count=4000)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    assert s.id is not None
    assert s.default_tone == "technical"


@pytest.mark.asyncio(loop_scope="function")
async def test_job_model_insert(db):
    from api.models import Job, Settings
    j = Job(topic="Test topic", tone="informative", word_count=3500, status="pending")
    db.add(j)
    await db.commit()
    await db.refresh(j)
    assert isinstance(j.id, uuid.UUID)
    assert j.status == "pending"
    assert j.created_at is not None


import pytest_asyncio
from api.auth import hash_password
from api.models import Settings


@pytest_asyncio.fixture
async def seeded_settings(db):
    """Ensure a Settings row exists; insert one if absent."""
    from sqlalchemy import select as _select
    result = await db.execute(_select(Settings))
    s = result.scalar_one_or_none()
    if s is None:
        s = Settings(password_hash=hash_password("testpass"))
        db.add(s)
        await db.commit()
    return s


async def test_get_settings_unauthenticated(client):
    resp = await client.get("/settings")
    assert resp.status_code == 401


async def test_get_settings(authed_client, seeded_settings):
    resp = await authed_client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_tone"] == "informative and insightful"
    assert data["default_word_count"] == 3500


async def test_update_settings(authed_client, seeded_settings):
    resp = await authed_client.put("/settings", json={"default_tone": "technical", "default_word_count": 4000})
    assert resp.status_code == 200
    assert resp.json()["default_tone"] == "technical"


async def test_change_password(authed_client, seeded_settings):
    resp = await authed_client.put(
        "/settings/password",
        json={"new_password": "newpass123", "confirm_password": "newpass123"},
    )
    assert resp.status_code == 200


async def test_change_password_mismatch(authed_client, seeded_settings):
    resp = await authed_client.put(
        "/settings/password",
        json={"new_password": "newpass123", "confirm_password": "different"},
    )
    assert resp.status_code == 400
