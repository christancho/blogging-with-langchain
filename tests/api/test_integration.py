import pytest
import pytest_asyncio
from api.models import Settings
from api.auth import hash_password


@pytest_asyncio.fixture
async def seeded_settings(db):
    s = Settings(password_hash=hash_password("testpass"))
    db.add(s)
    await db.commit()
    return s


async def test_login_sets_cookie(client, seeded_settings):
    resp = await client.post("/auth/login", json={"password": "testpass"})
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


async def test_login_wrong_password(client, seeded_settings):
    resp = await client.post("/auth/login", json={"password": "wrongpassword"})
    assert resp.status_code == 401


async def test_auth_me_authenticated(authed_client):
    resp = await authed_client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True


async def test_auth_me_unauthenticated(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_logout_clears_cookie(authed_client):
    resp = await authed_client.post("/auth/logout")
    assert resp.status_code == 200
    # Check cookie is cleared in response headers
    assert resp.headers.get("set-cookie", "").startswith("access_token=;") or \
           "access_token" not in authed_client.cookies or \
           not authed_client.cookies.get("access_token")


async def test_full_job_queue_flow(authed_client):
    # Create a job
    create_resp = await authed_client.post("/jobs", json={
        "topic": "Integration test topic",
        "tone": "informative",
        "word_count": 3500,
    })
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    # List shows it
    list_resp = await authed_client.get("/jobs")
    ids = [j["id"] for j in list_resp.json()]
    assert job_id in ids

    # Get returns it with result=None (not yet run)
    get_resp = await authed_client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["result"] is None

    # Delete it
    del_resp = await authed_client.delete(f"/jobs/{job_id}")
    assert del_resp.status_code == 204

    # Confirm gone
    assert (await authed_client.get(f"/jobs/{job_id}")).status_code == 404
