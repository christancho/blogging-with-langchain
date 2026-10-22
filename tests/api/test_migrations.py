import os
import subprocess
import sys
import uuid
import asyncpg
from api.pg_dsn import plain_dsn

DSN = plain_dsn(os.environ["DATABASE_URL"])
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_alembic_upgrade_head_on_fresh_database():
    """Run migrations exactly as the API container does on startup.

    The Dockerfile runs `alembic upgrade head` with the app's asyncpg
    DATABASE_URL before uvicorn starts; if it fails, the container never
    becomes healthy and the deploy rolls back. The rest of the suite builds
    the schema with create_all, so without this test a broken migration path
    (e.g. a driver change in a SQLAlchemy upgrade) goes unnoticed.
    """
    db_name = f"migr_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(DSN)
    await admin.execute(f'CREATE DATABASE "{db_name}"')
    try:
        base, _, _ = DSN.rpartition("/")
        env = {**os.environ, "DATABASE_URL": f"{base}/{db_name}".replace("postgresql://", "postgresql+asyncpg://", 1)}
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "--config", "api/alembic.ini", "upgrade", "head"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]

        conn = await asyncpg.connect(f"{base}/{db_name}")
        try:
            tables = {r["tablename"] for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
            trigger = await conn.fetchval("SELECT tgname FROM pg_trigger WHERE tgname = 'jobs_changed_notify'")
        finally:
            await conn.close()
        assert {"jobs", "settings", "alembic_version"} <= tables
        assert trigger == "jobs_changed_notify"
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        await admin.close()
