import asyncio
import os
import socket
import subprocess
import sys
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# NOTE: Tests require a running Postgres instance.
# Start one with Docker: docker run -d --name blogforge-test-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/blogforge_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-bytes-minimum!")
os.environ.setdefault("UI_PASSWORD", "testpass")
os.environ.setdefault("WEB_URL", "http://localhost:3000")
os.environ.setdefault("ENV", "test")

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
assert "blogforge_test" in TEST_DATABASE_URL, "Must use test database — set DATABASE_URL to point at blogforge_test"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    from api.db import Base
    import api.models  # noqa: F401 — registers models with Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine):
    """Provide a transactional session that rolls back after each test."""
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await conn.rollback()


@pytest_asyncio.fixture
async def client(db):
    from api.main import app
    from api.db import get_db

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authed_client(client, db):
    """Client with a valid auth cookie already set."""
    from api.models import Settings
    from api.auth import hash_password
    from sqlalchemy import select

    result = await db.execute(select(Settings))
    if not result.scalar_one_or_none():
        db.add(Settings(password_hash=hash_password("testpass")))
        await db.commit()

    resp = await client.post("/auth/login", json={"password": "testpass"})
    assert resp.status_code == 200
    return client


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest_asyncio.fixture
async def live_server(test_engine):
    """Run the real app in a uvicorn subprocess bound to a free port.

    A separate OS process (rather than an in-process background thread) is
    used deliberately: `api.db.engine` is a module-level singleton whose
    asyncpg connections are bound to whatever event loop first uses them. A
    background thread would run its own event loop, and reusing the engine
    from a second loop within the same process risks
    "Future attached to a different loop" errors. A subprocess gets its own
    fresh interpreter, engine, and loop, matching how the app actually runs.

    Depends on `test_engine` (from conftest.py) purely for its side effect of
    creating the schema before this fixture starts the subprocess, and not
    dropping it until after the subprocess is killed — this fixture doesn't
    otherwise touch that engine/connection (the subprocess has its own).
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO_ROOT,
        env=env,
    )
    try:
        async with AsyncClient(base_url=base_url) as probe:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError(f"live server process exited early with code {proc.returncode}")
                try:
                    resp = await probe.get("/health", timeout=1)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError("live server did not become ready in time")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest_asyncio.fixture
async def authed_live_client(live_server):
    """AsyncClient hitting the real live_server, already logged in."""
    async with AsyncClient(base_url=live_server) as c:
        resp = await c.post("/auth/login", json={"password": os.environ.get("UI_PASSWORD", "testpass")})
        assert resp.status_code == 200, resp.text
        yield c
