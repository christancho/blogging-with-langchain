import os
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
