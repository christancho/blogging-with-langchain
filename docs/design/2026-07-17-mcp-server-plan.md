# Remote MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing LangGraph blog pipeline as a remote MCP server (mounted into the current FastAPI app) so blogs can be generated, reviewed, and published from Claude Desktop.

**Architecture:** A `FastMCP` server is built in `api/mcp_server.py`, its tools calling the existing domain layer (`Job`/`Settings` models, `publisher_node`) in-process via an injected async session factory. Auth is verification-only: `api/mcp_auth.py` validates the provider's JWT against its JWKS. The MCP ASGI app is mounted into `api/main.py` at the root so its `/mcp` endpoint and OAuth metadata are served alongside the existing REST API, sharing the process, DB, and background worker.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, MCP Python SDK (`mcp`), PyJWT (JWKS verification), pytest / pytest-asyncio.

> **Corrections applied during implementation** (the code below is the original plan; these are the deltas in what actually shipped):
> - `_curate_result` reads **`meta_description`** (the real pipeline state key), not `seo_description`, and computes **`word_count`** from `final_content` (`len(final_content.split())`) rather than reading a non-existent `word_count` key. The `seo_description`/`word_count` snippets in Task 3 below are the pre-correction versions.
> - Auth fails **closed in production**: `api/mcp_auth.py` adds `require_auth_config_or_warn(...)`, called at startup — it raises when `ENV=production` and OAuth env is incomplete, and warns (runs unauthenticated) otherwise.
> - `update_settings_impl` validates `llm_temperature` to the 0.0–2.0 bound the REST route enforces.

## Global Constraints

- Pin the MCP SDK: `mcp==1.28.1` (verified API surface below). Import paths: `from mcp.server.fastmcp import FastMCP`, `from mcp.server.auth.provider import TokenVerifier, AccessToken`, `from mcp.server.auth.settings import AuthSettings`. The `MCPServer` name in some online docs is unreleased — do NOT use it.
- Auth libs are already project deps — do NOT add new ones: `PyJWT==2.10.1` (use `jwt.PyJWKClient`), `cryptography` (via `python-jose[cryptography]==3.5.0`).
- No new REST endpoints and no changes to the LangGraph pipeline, worker, or existing routes.
- Repo rule — **no silent error swallowing**: every `except` must at least print the error. Fallbacks must remain visible.
- MCP tools must NOT use FastAPI dependency injection. They call the domain layer directly through an injected `session_factory` (an `async_sessionmaker`), so they are unit-testable against a test-engine factory.
- Tests require a running Postgres test DB (see `tests/api/conftest.py`); `ENV=test` disables worker autostart.
- Provider is pluggable via env only (`OAUTH_ISSUER`, `OAUTH_AUDIENCE`, `OAUTH_JWKS_URL`, `MCP_RESOURCE_URL`). Default recommended provider: Stytch (WorkOS AuthKit is a drop-in alternative). No provider SDK is imported.

---

## File Structure

- **Create** `api/mcp_auth.py` — `JwksTokenVerifier(TokenVerifier)`, `build_token_verifier()`, `build_auth_settings()`.
- **Create** `api/mcp_server.py` — tool implementation functions (`*_impl`), `_serialize_job`, `_curate_result`, `_settings_dict`, and `build_mcp(session_factory, token_verifier, auth_settings)`.
- **Modify** `api/main.py` — build the MCP app, wire its `session_manager` into the existing lifespan, mount at `/`.
- **Modify** `requirements.txt` — add `mcp==1.28.1`.
- **Modify** `.env.example` — add the four OAuth vars.
- **Create** `tests/api/test_mcp_auth.py` — verifier unit tests.
- **Create** `tests/api/test_mcp_tools.py` — tool unit tests + one in-memory integration test.

---

## Task 1: Add dependency and OAuth env config

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

**Interfaces:**
- Produces: env var contract `OAUTH_ISSUER`, `OAUTH_AUDIENCE`, `OAUTH_JWKS_URL`, `MCP_RESOURCE_URL`.

- [ ] **Step 1: Add the SDK to requirements**

Add this line to `requirements.txt` (near the other server deps like `fastapi`/`uvicorn`):

```
mcp==1.28.1
```

- [ ] **Step 2: Install it**

Run: `pip install -r requirements.txt`
Expected: installs `mcp` 1.28.1 and its deps with no conflicts.

- [ ] **Step 3: Verify the import surface**

Run:
```bash
python -c "from mcp.server.fastmcp import FastMCP; from mcp.server.auth.provider import TokenVerifier, AccessToken; from mcp.server.auth.settings import AuthSettings; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 4: Document env vars**

Append to `.env.example`:

```env
# --- Remote MCP server (OAuth verification) ---
# Managed OAuth provider (Stytch recommended; WorkOS AuthKit alternative).
# When all four are set, the /mcp endpoint requires a valid bearer token.
OAUTH_ISSUER=https://your-project.stytch.dev
OAUTH_AUDIENCE=https://your-domain.example.com/mcp
OAUTH_JWKS_URL=https://your-project.stytch.dev/.well-known/jwks.json
MCP_RESOURCE_URL=https://your-domain.example.com/mcp
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add mcp SDK dependency and OAuth env config"
```

---

## Task 2: JWKS token verifier

**Files:**
- Create: `api/mcp_auth.py`
- Test: `tests/api/test_mcp_auth.py`

**Interfaces:**
- Produces:
  - `class JwksTokenVerifier(TokenVerifier)` with `async def verify_token(self, token: str) -> AccessToken | None`.
  - `build_token_verifier() -> JwksTokenVerifier | None` (None when any of `OAUTH_JWKS_URL`/`OAUTH_ISSUER`/`OAUTH_AUDIENCE` is unset).
  - `build_auth_settings() -> AuthSettings | None` (None when `OAUTH_ISSUER` or `MCP_RESOURCE_URL` is unset).

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_mcp_auth.py`:

```python
import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from api.mcp_auth import JwksTokenVerifier


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


def _make_token(priv_pem, **overrides):
    payload = {
        "iss": "https://issuer.test",
        "aud": "https://mcp.test",
        "sub": "user-1",
        "exp": int(time.time()) + 3600,
        "scope": "blog:generate",
        **overrides,
    }
    return jwt.encode(payload, priv_pem, algorithm="RS256")


class _FakeSigningKey:
    def __init__(self, key_pem):
        self.key = key_pem


@pytest.fixture
def verifier(monkeypatch, rsa_keypair):
    _, pub_pem = rsa_keypair
    from jwt import PyJWKClient
    monkeypatch.setattr(
        PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, token: _FakeSigningKey(pub_pem),
    )
    return JwksTokenVerifier(
        jwks_url="https://issuer.test/.well-known/jwks.json",
        issuer="https://issuer.test",
        audience="https://mcp.test",
    )


async def test_valid_token_accepted(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem)
    result = await verifier.verify_token(token)
    assert result is not None
    assert result.subject == "user-1"
    assert "blog:generate" in result.scopes


async def test_expired_token_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem, exp=int(time.time()) - 10)
    assert await verifier.verify_token(token) is None


async def test_wrong_issuer_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem, iss="https://evil.test")
    assert await verifier.verify_token(token) is None


async def test_wrong_audience_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem, aud="https://other.test")
    assert await verifier.verify_token(token) is None


async def test_bad_signature_rejected(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = _make_token(other_pem)  # signed by a key the verifier won't accept
    assert await verifier.verify_token(token) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_mcp_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.mcp_auth'`.

- [ ] **Step 3: Write the implementation**

Create `api/mcp_auth.py`:

```python
import os

import jwt
from jwt import PyJWKClient

from mcp.server.auth.provider import TokenVerifier, AccessToken
from mcp.server.auth.settings import AuthSettings


class JwksTokenVerifier(TokenVerifier):
    """Verify a provider-issued JWT against the provider's JWKS.

    Validates signature (RS256), issuer, and audience. Returns an AccessToken
    on success or None on any failure (the MCP SDK turns None into a 401).
    """

    def __init__(self, jwks_url: str, issuer: str, audience: str):
        self.jwks_client = PyJWKClient(jwks_url)
        self.issuer = issuer
        self.audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception as e:  # noqa: BLE001 — must stay visible per repo rule
            print(f"[mcp-auth] token verification failed: {e}")
            return None

        scope = claims.get("scope", "")
        return AccessToken(
            token=token,
            client_id=claims.get("client_id", claims.get("azp", "unknown")),
            scopes=scope.split() if scope else [],
            expires_at=claims.get("exp"),
            subject=claims.get("sub"),
            claims=claims,
        )


def build_token_verifier() -> JwksTokenVerifier | None:
    """Build the verifier from env, or None if OAuth is not configured."""
    jwks_url = os.environ.get("OAUTH_JWKS_URL")
    issuer = os.environ.get("OAUTH_ISSUER")
    audience = os.environ.get("OAUTH_AUDIENCE")
    if not (jwks_url and issuer and audience):
        print("[mcp-auth] OAuth env not fully set — MCP server will run UNAUTHENTICATED")
        return None
    return JwksTokenVerifier(jwks_url, issuer, audience)


def build_auth_settings() -> AuthSettings | None:
    """Build AuthSettings (advertised discovery metadata) from env, or None."""
    issuer = os.environ.get("OAUTH_ISSUER")
    resource = os.environ.get("MCP_RESOURCE_URL")
    if not (issuer and resource):
        return None
    return AuthSettings(
        issuer_url=issuer,
        resource_server_url=resource,
        required_scopes=[],
    )
```

> Note: `PyJWKClient.get_signing_key_from_jwt` is synchronous and fetches/caches the JWKS on first use; the brief blocking call inside `verify_token` is acceptable (cached thereafter), mirroring how the REST layer already makes blocking calls.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_mcp_auth.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add api/mcp_auth.py tests/api/test_mcp_auth.py
git commit -m "feat: add JWKS token verifier for MCP OAuth"
```

---

## Task 3: Read tools (generate, get, list, logs) + helpers

**Files:**
- Create: `api/mcp_server.py`
- Test: `tests/api/test_mcp_tools.py`

**Interfaces:**
- Consumes: `api.models.Job`, `api.models.Settings`; `agentic.config.Config`.
- Produces (all take `session_factory` as first arg — an `async_sessionmaker`):
  - `async def generate_blog_impl(session_factory, topic, tone=None, word_count=None, instructions=None) -> dict` → `{"job_id": str, "status": str}`
  - `async def get_job_impl(session_factory, job_id) -> dict` (curated, includes `result` when completed; raises `ValueError` if not found)
  - `async def list_jobs_impl(session_factory, limit=20) -> list[dict]`
  - `async def get_job_logs_impl(session_factory, job_id) -> dict` → `{"logs": str}`
  - `_serialize_job(job, include_result=False) -> dict`, `_curate_result(result) -> dict | None`

- [ ] **Step 1: Add a test session-factory fixture and write the failing tests**

Create `tests/api/test_mcp_tools.py`:

```python
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select

from api.models import Job, Settings
from api.auth import hash_password
from api.mcp_server import (
    generate_blog_impl,
    get_job_impl,
    list_jobs_impl,
    get_job_logs_impl,
)


@pytest_asyncio.fixture
async def session_factory(test_engine):
    """A real async_sessionmaker bound to the test engine.

    MCP tools open their own sessions (no FastAPI DI), so tests give them a
    factory on the test engine. The function-scoped test_engine drops all
    tables afterward, cleaning up committed rows.
    """
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_settings(session_factory):
    async with session_factory() as db:
        existing = (await db.execute(select(Settings))).scalar_one_or_none()
        if existing is None:
            db.add(Settings(password_hash=hash_password("testpass")))
            await db.commit()


async def test_generate_blog_inserts_pending(session_factory, seeded_settings):
    out = await generate_blog_impl(session_factory, topic="AI in healthcare")
    assert out["status"] == "pending"
    assert uuid.UUID(out["job_id"])  # parses as a UUID
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.topic == "AI in healthcare"
        assert job.status == "pending"


async def test_generate_blog_uses_settings_defaults(session_factory, seeded_settings):
    out = await generate_blog_impl(session_factory, topic="Defaults test")
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.tone == "informative and insightful"   # Settings default
        assert job.word_count == 3500                       # Settings default


async def test_generate_blog_explicit_args_win(session_factory, seeded_settings):
    out = await generate_blog_impl(
        session_factory, topic="X", tone="casual", word_count=1200, instructions="be brief"
    )
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.tone == "casual"
        assert job.word_count == 1200
        assert job.instructions == "be brief"


async def test_get_job_returns_curated_result(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(
            topic="Done", tone="informative", word_count=3500, status="completed",
            result={
                "final_content": "# Title\n\nBody",
                "seo_title": "SEO Title",
                "seo_description": "desc",
                "tags": ["ai", "health"],
                "warnings": ["force_published"],
                "secret_internal_field": "should not leak",
            },
        )
        db.add(job)
        await db.commit()
        job_id = str(job.id)

    out = await get_job_impl(session_factory, job_id)
    assert out["status"] == "completed"
    assert out["result"]["final_content"] == "# Title\n\nBody"
    assert out["result"]["seo_title"] == "SEO Title"
    assert out["result"]["tags"] == ["ai", "health"]
    assert out["result"]["warnings"] == ["force_published"]
    assert "secret_internal_field" not in out["result"]


async def test_get_job_not_found_raises(session_factory, seeded_settings):
    with pytest.raises(ValueError, match="Job not found"):
        await get_job_impl(session_factory, str(uuid.uuid4()))


async def test_list_jobs_newest_first(session_factory, seeded_settings):
    await generate_blog_impl(session_factory, topic="First")
    await generate_blog_impl(session_factory, topic="Second")
    jobs = await list_jobs_impl(session_factory, limit=10)
    assert len(jobs) >= 2
    assert jobs[0]["created_at"] >= jobs[1]["created_at"]
    assert "result" not in jobs[0]  # list is lightweight, no curated result


async def test_get_job_logs(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="L", tone="t", word_count=100, status="running", logs="line1\nline2\n")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    out = await get_job_logs_impl(session_factory, job_id)
    assert out["logs"] == "line1\nline2\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_mcp_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.mcp_server'`.

- [ ] **Step 3: Write the implementation**

Create `api/mcp_server.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_mcp_tools.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add api/mcp_server.py tests/api/test_mcp_tools.py
git commit -m "feat: add MCP read tools (generate/get/list/logs)"
```

---

## Task 4: Action tools (publish, retry)

**Files:**
- Modify: `api/mcp_server.py`
- Test: `tests/api/test_mcp_tools.py`

**Interfaces:**
- Consumes: `agentic.nodes.publisher.publisher_node`.
- Produces:
  - `async def publish_blog_impl(session_factory, job_id) -> dict` → `{"url": str | None, "post_id": str | None}` (raises `ValueError` on not-found / non-completed / no-result / Ghost failure)
  - `async def retry_blog_impl(session_factory, job_id) -> dict` → `{"job_id": str, "status": str}` (raises `ValueError` on not-found / non-failed)

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_mcp_tools.py`:

```python
from api.mcp_server import publish_blog_impl, retry_blog_impl


async def test_publish_non_completed_rejected(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="P", tone="t", word_count=100, status="pending")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    with pytest.raises(ValueError, match="Only completed jobs can be published"):
        await publish_blog_impl(session_factory, job_id)


async def test_publish_completed_calls_publisher(session_factory, seeded_settings, monkeypatch):
    async with session_factory() as db:
        job = Job(
            topic="P", tone="t", word_count=100, status="completed",
            result={"final_content": "# T\n\nB", "seo_title": "T"},
        )
        db.add(job)
        await db.commit()
        job_id = str(job.id)

    def fake_publisher(state):
        return {
            "publication_status": "published",
            "ghost_post_url": "https://ghost.test/p/1",
            "ghost_post_id": "abc123",
        }
    monkeypatch.setattr("agentic.nodes.publisher.publisher_node", fake_publisher)

    out = await publish_blog_impl(session_factory, job_id)
    assert out["url"] == "https://ghost.test/p/1"
    assert out["post_id"] == "abc123"
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(job_id))
        assert job.status == "published"


async def test_publish_surfaces_ghost_failure(session_factory, seeded_settings, monkeypatch):
    async with session_factory() as db:
        job = Job(
            topic="P", tone="t", word_count=100, status="completed",
            result={"final_content": "# T"},
        )
        db.add(job)
        await db.commit()
        job_id = str(job.id)

    def fake_publisher(state):
        return {"publication_status": "failed", "errors": ["Ghost 401 Unauthorized"]}
    monkeypatch.setattr("agentic.nodes.publisher.publisher_node", fake_publisher)

    with pytest.raises(ValueError, match="Ghost 401 Unauthorized"):
        await publish_blog_impl(session_factory, job_id)


async def test_retry_failed_job(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="Failed", tone="t", word_count=100, status="failed", error="boom")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    out = await retry_blog_impl(session_factory, job_id)
    assert out["status"] == "pending"
    async with session_factory() as db:
        new_job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert new_job.topic == "Failed"
        assert new_job.id != uuid.UUID(job_id)


async def test_retry_non_failed_rejected(session_factory, seeded_settings):
    async with session_factory() as db:
        job = Job(topic="Pending", tone="t", word_count=100, status="pending")
        db.add(job)
        await db.commit()
        job_id = str(job.id)
    with pytest.raises(ValueError, match="Only failed jobs can be retried"):
        await retry_blog_impl(session_factory, job_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_mcp_tools.py -k "publish or retry" -v`
Expected: FAIL — `ImportError: cannot import name 'publish_blog_impl'`.

- [ ] **Step 3: Write the implementation**

Append to `api/mcp_server.py`:

```python
async def publish_blog_impl(session_factory, job_id) -> dict:
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(str(job_id)))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        if job.status != "completed":
            raise ValueError("Only completed jobs can be published")
        if not job.result:
            raise ValueError("Job has no result to publish")

        from agentic.nodes.publisher import publisher_node
        state_updates = publisher_node(job.result)

        if state_updates.get("publication_status") == "failed":
            errors = state_updates.get("errors", ["Ghost publish failed"])
            raise ValueError(errors[-1])

        job.status = "published"
        job.result = {**job.result, **state_updates}
        await db.commit()
        return {
            "url": state_updates.get("ghost_post_url"),
            "post_id": state_updates.get("ghost_post_id"),
        }


async def retry_blog_impl(session_factory, job_id) -> dict:
    async with session_factory() as db:
        original = await db.get(Job, uuid.UUID(str(job_id)))
        if not original:
            raise ValueError(f"Job not found: {job_id}")
        if original.status != "failed":
            raise ValueError("Only failed jobs can be retried")
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
        return {"job_id": str(new_job.id), "status": new_job.status}
```

> Note: the test monkeypatches `agentic.nodes.publisher.publisher_node`, and the impl imports it *inside* the function, so the patched symbol is used. This mirrors the existing REST publish route exactly (including the `publication_status == "failed"` check).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_mcp_tools.py -k "publish or retry" -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add api/mcp_server.py tests/api/test_mcp_tools.py
git commit -m "feat: add MCP action tools (publish/retry)"
```

---

## Task 5: Settings tools (get, update)

**Files:**
- Modify: `api/mcp_server.py`
- Test: `tests/api/test_mcp_tools.py`

**Interfaces:**
- Produces:
  - `async def get_settings_impl(session_factory) -> dict`
  - `async def update_settings_impl(session_factory, default_tone=None, default_word_count=None, llm_temperature=None, llm_model=None, auto_publish_to_ghost=None) -> dict`
  - `_settings_dict(s) -> dict`

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_mcp_tools.py`:

```python
from api.mcp_server import get_settings_impl, update_settings_impl


async def test_get_settings(session_factory, seeded_settings):
    out = await get_settings_impl(session_factory)
    assert out["default_tone"] == "informative and insightful"
    assert out["default_word_count"] == 3500
    assert "password_hash" not in out


async def test_update_settings_partial(session_factory, seeded_settings):
    out = await update_settings_impl(session_factory, default_tone="snarky", auto_publish_to_ghost=False)
    assert out["default_tone"] == "snarky"
    assert out["auto_publish_to_ghost"] is False
    assert out["default_word_count"] == 3500  # untouched field unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_mcp_tools.py -k "settings" -v`
Expected: FAIL — `ImportError: cannot import name 'get_settings_impl'`.

- [ ] **Step 3: Write the implementation**

Append to `api/mcp_server.py`:

```python
def _settings_dict(s: Settings) -> dict:
    return {
        "default_tone": s.default_tone,
        "default_word_count": s.default_word_count,
        "llm_temperature": s.llm_temperature,
        "llm_model": s.llm_model,
        "auto_publish_to_ghost": s.auto_publish_to_ghost,
    }


async def get_settings_impl(session_factory) -> dict:
    async with session_factory() as db:
        s = (await db.execute(select(Settings))).scalar_one()
        return _settings_dict(s)


async def update_settings_impl(
    session_factory,
    default_tone=None,
    default_word_count=None,
    llm_temperature=None,
    llm_model=None,
    auto_publish_to_ghost=None,
) -> dict:
    async with session_factory() as db:
        s = (await db.execute(select(Settings))).scalar_one()
        if default_tone is not None:
            s.default_tone = default_tone
        if default_word_count is not None:
            s.default_word_count = default_word_count
        if llm_temperature is not None:
            s.llm_temperature = llm_temperature
        if llm_model is not None:
            s.llm_model = llm_model
        if auto_publish_to_ghost is not None:
            s.auto_publish_to_ghost = auto_publish_to_ghost
        await db.commit()
        await db.refresh(s)
        return _settings_dict(s)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/test_mcp_tools.py -k "settings" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add api/mcp_server.py tests/api/test_mcp_tools.py
git commit -m "feat: add MCP settings tools (get/update)"
```

---

## Task 6: Assemble the FastMCP server (`build_mcp`) + integration test

**Files:**
- Modify: `api/mcp_server.py`
- Test: `tests/api/test_mcp_tools.py`

**Interfaces:**
- Consumes: all `*_impl` functions above; `FastMCP`; optional `TokenVerifier` + `AuthSettings`.
- Produces: `def build_mcp(session_factory, token_verifier=None, auth_settings=None) -> FastMCP` registering tools `generate_blog`, `get_job`, `list_jobs`, `get_job_logs`, `publish_blog`, `retry_blog`, `get_settings`, `update_settings`. When `token_verifier` and `auth_settings` are both provided, the server enforces bearer auth; otherwise it runs unauthenticated (used by tests).

- [ ] **Step 1: Write the failing integration test**

Append to `tests/api/test_mcp_tools.py`:

```python
from mcp.shared.memory import create_connected_server_and_client_session
from api.mcp_server import build_mcp


async def test_tools_listed_and_callable_in_memory(session_factory, seeded_settings):
    mcp = build_mcp(session_factory)  # no auth for the in-memory client

    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        await client.initialize()

        tools = {t.name for t in (await client.list_tools()).tools}
        assert {
            "generate_blog", "get_job", "list_jobs", "get_job_logs",
            "publish_blog", "retry_blog", "get_settings", "update_settings",
        } <= tools

        created = await client.call_tool("generate_blog", {"topic": "End to end"})
        assert created.isError is False
        job_id = created.structuredContent["job_id"]

        fetched = await client.call_tool("get_job", {"job_id": job_id})
        assert fetched.isError is False
        assert fetched.structuredContent["status"] == "pending"

        missing = await client.call_tool("get_job", {"job_id": str(uuid.uuid4())})
        assert missing.isError is True  # ValueError becomes a tool error
```

> `build_mcp` returns a `FastMCP`; the in-memory helper connects to its lower-level server via `mcp._mcp_server`. `call_tool` returns a `CallToolResult` whose `.structuredContent` holds the tool's returned dict and `.isError` reflects raised exceptions.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_mcp_tools.py -k "in_memory" -v`
Expected: FAIL — `ImportError: cannot import name 'build_mcp'`.

- [ ] **Step 3: Write the implementation**

Append to `api/mcp_server.py` (add `from mcp.server.fastmcp import FastMCP` at the top of the file with the other imports):

```python
def build_mcp(session_factory, token_verifier=None, auth_settings=None) -> "FastMCP":
    """Build the BlogForge MCP server. Tools bind to the given session factory.

    When both token_verifier and auth_settings are provided, all tools require a
    valid bearer token; otherwise the server runs unauthenticated (tests only).
    """
    kwargs = {"name": "BlogForge", "streamable_http_path": "/mcp"}
    if token_verifier is not None and auth_settings is not None:
        kwargs["token_verifier"] = token_verifier
        kwargs["auth"] = auth_settings
    mcp = FastMCP(**kwargs)

    @mcp.tool()
    async def generate_blog(
        topic: str,
        tone: str | None = None,
        word_count: int | None = None,
        instructions: str | None = None,
    ) -> dict:
        """Queue a new blog-generation job. Returns a job_id to poll with get_job."""
        return await generate_blog_impl(session_factory, topic, tone, word_count, instructions)

    @mcp.tool()
    async def get_job(job_id: str) -> dict:
        """Get a job's status and, once completed, the finished article for review."""
        return await get_job_impl(session_factory, job_id)

    @mcp.tool()
    async def list_jobs(limit: int = 20) -> list[dict]:
        """List recent blog jobs, newest first."""
        return await list_jobs_impl(session_factory, limit)

    @mcp.tool()
    async def get_job_logs(job_id: str) -> dict:
        """Get the captured pipeline log output for a job."""
        return await get_job_logs_impl(session_factory, job_id)

    @mcp.tool()
    async def publish_blog(job_id: str) -> dict:
        """Publish a completed job's article to Ghost CMS."""
        return await publish_blog_impl(session_factory, job_id)

    @mcp.tool()
    async def retry_blog(job_id: str) -> dict:
        """Re-queue a failed job as a new pending job."""
        return await retry_blog_impl(session_factory, job_id)

    @mcp.tool()
    async def get_settings() -> dict:
        """Get current generation defaults and settings."""
        return await get_settings_impl(session_factory)

    @mcp.tool()
    async def update_settings(
        default_tone: str | None = None,
        default_word_count: int | None = None,
        llm_temperature: float | None = None,
        llm_model: str | None = None,
        auto_publish_to_ghost: bool | None = None,
    ) -> dict:
        """Update one or more generation settings."""
        return await update_settings_impl(
            session_factory,
            default_tone,
            default_word_count,
            llm_temperature,
            llm_model,
            auto_publish_to_ghost,
        )

    return mcp
```

- [ ] **Step 4: Run the full MCP test suite to verify it passes**

Run: `pytest tests/api/test_mcp_tools.py tests/api/test_mcp_auth.py -v`
Expected: PASS (all tasks 2–6 tests green).

- [ ] **Step 5: Commit**

```bash
git add api/mcp_server.py tests/api/test_mcp_tools.py
git commit -m "feat: assemble FastMCP server with all blog tools"
```

---

## Task 7: Mount into FastAPI and wire the lifespan

**Files:**
- Modify: `api/main.py`

**Interfaces:**
- Consumes: `build_mcp`, `build_token_verifier`, `build_auth_settings`, `AsyncSessionLocal`.
- Produces: the running app serves `POST /mcp` (MCP endpoint) and the OAuth discovery metadata, alongside the existing REST routes and background worker.

- [ ] **Step 1: Build the MCP app and integrate the session manager**

In `api/main.py`, add imports near the existing `from api.routes import ...` lines:

```python
from api.db import get_db, AsyncSessionLocal
from api.mcp_server import build_mcp
from api.mcp_auth import build_token_verifier, build_auth_settings
```

Immediately BEFORE the `lifespan` definition, construct the MCP app (so its session manager exists before the app starts):

```python
mcp = build_mcp(AsyncSessionLocal, build_token_verifier(), build_auth_settings())
mcp_app = mcp.streamable_http_app()  # creates the session manager; serves /mcp + metadata
```

- [ ] **Step 2: Run the MCP session manager inside the existing lifespan**

Wrap the existing lifespan body with the session manager. Replace the current `lifespan` function with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed settings, start the worker, and run the MCP session manager."""
    async with mcp.session_manager.run():
        try:
            _log.info("STARTUP [1/3] seeding settings...")
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Settings))
                if not result.scalar_one_or_none():
                    initial_password = os.environ.get("UI_PASSWORD", "changeme")
                    db.add(Settings(password_hash=hash_password(initial_password)))
                    await db.commit()
            _log.info("STARTUP [1/3] settings seeded")

            if os.environ.get("ENV") != "test":
                _log.info("STARTUP [2/3] importing worker module...")
                from api.worker import start_worker
                _log.info("STARTUP [2/3] starting background worker...")
                start_worker()
                _log.info("STARTUP [2/3] background worker started")

            _log.info("STARTUP [3/3] complete — app ready")
        except Exception:
            _log.error("STARTUP FAILED:\n" + traceback.format_exc())
            raise
        yield
```

- [ ] **Step 3: Mount the MCP app AFTER the existing routers**

At the very end of `api/main.py` (after `app.include_router(jobs_router.router)` and all `@app.*` route definitions), add:

```python
# Mount the MCP ASGI app at root LAST so specific REST routes match first.
# It serves POST /mcp and the OAuth protected-resource metadata.
app.mount("/", mcp_app)
```

- [ ] **Step 4: Verify the app imports and existing tests still pass**

Run: `ENV=test python -c "import api.main; print('import ok')"`
Expected: prints `import ok` (no OAuth env set → logs an UNAUTHENTICATED warning, which is fine for local/test).

Run: `pytest tests/api -q`
Expected: PASS — existing REST/worker tests and the new MCP tests all green.

- [ ] **Step 5: Verify the MCP endpoint and metadata are served (manual, local)**

Start the app locally (with a test Postgres running and `DATABASE_URL`/`JWT_SECRET` set, OAuth vars left unset for this smoke test):

```bash
uvicorn api.main:app --port 8000
```

In another shell:

```bash
# MCP endpoint responds (unauthenticated in this smoke test):
curl -sS -i -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -30

# Existing REST route still works:
curl -sS http://localhost:8000/health
```

Expected: the `/mcp` POST returns a JSON-RPC response listing the eight tools; `/health` returns `{"status":"ok"}`.

Then set the four OAuth env vars (real Stytch/WorkOS values) and restart; confirm the discovery metadata is exposed:

```bash
curl -sS http://localhost:8000/.well-known/oauth-protected-resource | head -20
```

Expected: JSON metadata referencing your `MCP_RESOURCE_URL` and the provider's `issuer`. (If the path differs in this SDK build, note the actual path returned in the response headers of an unauthenticated `/mcp` call — the `WWW-Authenticate` header points at the resource-metadata URL.)

- [ ] **Step 6: Commit**

```bash
git add api/main.py
git commit -m "feat: mount MCP server into FastAPI app with shared lifespan"
```

---

## Post-Implementation: Provider + Claude Desktop setup (manual, not code)

1. Create an application in the OAuth provider (Stytch "Connected Apps" recommended; WorkOS AuthKit alternative).
2. Enable **dynamic client registration** for that app.
3. Set the deployment env: `OAUTH_ISSUER`, `OAUTH_AUDIENCE` (= your `/mcp` URL), `OAUTH_JWKS_URL`, `MCP_RESOURCE_URL` (= your `/mcp` URL). Deploy.
4. In Claude Desktop → Settings → Connectors → Add custom connector → enter `https://<your-domain>/mcp`. Complete the one-time sign-in via the provider.
5. Smoke test end-to-end: ask Claude to `generate_blog` a topic, poll `get_job`, review the returned `final_content`, then `publish_blog`.

---

## Self-Review

**Spec coverage:**
- Single-service mount → Task 7. ✓
- Direct in-process domain calls (no self-HTTP) → Tasks 3–5 (impls use `session_factory` + models/`publisher_node`). ✓
- Managed-OAuth, verify-only → Task 2 + Task 7 wiring. ✓
- Fire-and-poll `generate_blog` → Task 3. ✓
- Curated `get_job` with `final_content` for review → Task 3 (`_curate_result`, leak test). ✓
- Full tool catalog (8 tools, `delete_job` deferred) → Tasks 3–6. ✓
- Error handling: status guards, Ghost error surfaced, worker errors via `get_job.error`, auth 401 → Tasks 3–4 (`ValueError` tests) + Task 2. ✓
- Testing: unit tools, unit auth, in-memory integration, manual connect → Tasks 2–7. ✓
- Repo changes list (requirements, mcp_server, mcp_auth, main, .env.example) → all covered. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every command has expected output. ✓

**Type consistency:** `session_factory`-first signatures consistent across Tasks 3–6; `build_mcp(session_factory, token_verifier=None, auth_settings=None)` matches Task 7's call; `_curate_result`/`_serialize_job`/`_settings_dict` names consistent; tool names identical between Task 6 registration and Task 6 integration-test assertions. ✓

**Note on one intentional deviation from REST:** `generate_blog_impl` reads defaults from the `Settings` row (falling back to `Config`), whereas the REST `create_job` uses `Config` directly. This is deliberate — the `Settings` row is the user-editable default — and is covered by `test_generate_blog_uses_settings_defaults`.
