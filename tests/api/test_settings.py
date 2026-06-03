import pytest
import uuid
from sqlalchemy import text
from unittest.mock import patch, AsyncMock, MagicMock
import os


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
async def test_settings_model_has_llm_fields(db):
    from api.models import Settings
    from api.auth import hash_password
    s = Settings(password_hash=hash_password("secret"))
    db.add(s)
    await db.commit()
    await db.refresh(s)
    assert s.llm_temperature == 0.7
    assert s.llm_model == "anthropic/claude-sonnet-4-5"


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


@pytest.mark.asyncio(loop_scope="function")
async def test_get_settings_includes_llm_fields(authed_client, seeded_settings):
    resp = await authed_client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_temperature" in data
    assert "llm_model" in data
    assert data["llm_temperature"] == 0.7
    assert data["llm_model"] == "anthropic/claude-sonnet-4-5"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_llm_temperature(authed_client, seeded_settings):
    resp = await authed_client.put("/settings", json={"llm_temperature": 1.2})
    assert resp.status_code == 200
    assert resp.json()["llm_temperature"] == 1.2


@pytest.mark.asyncio(loop_scope="function")
async def test_update_llm_model(authed_client, seeded_settings):
    resp = await authed_client.put("/settings", json={"llm_model": "openai/gpt-4o"})
    assert resp.status_code == 200
    assert resp.json()["llm_model"] == "openai/gpt-4o"


@pytest.mark.asyncio(loop_scope="function")
async def test_list_models(authed_client, seeded_settings):
    fake_response = AsyncMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o", "name": "GPT-4o"},
            {"id": "anthropic/claude-sonnet-4-5", "name": "Claude Sonnet 4.5"},
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        with patch("api.routes.settings.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = fake_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            resp = await authed_client.get("/settings/models")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "anthropic/claude-sonnet-4-5"
    assert "name" in data[0]
    assert "name" in data[1]
    assert data[0]["name"].lower() < data[1]["name"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_list_models_unauthenticated(client):
    resp = await client.get("/settings/models")
    assert resp.status_code == 401


@pytest.mark.asyncio(loop_scope="function")
async def test_list_models_no_api_key(authed_client, seeded_settings):
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENROUTER_API_KEY", None)
        resp = await authed_client.get("/settings/models")
    assert resp.status_code == 503


@pytest.mark.asyncio(loop_scope="function")
async def test_update_llm_temperature_out_of_range(authed_client, seeded_settings):
    resp = await authed_client.put("/settings", json={"llm_temperature": 3.0})
    assert resp.status_code == 422
