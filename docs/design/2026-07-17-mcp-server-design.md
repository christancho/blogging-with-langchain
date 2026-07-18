# Remote MCP Server for Blog Generation — Design

**Date:** 2026-07-17
**Status:** Approved (design), pending implementation plan
**Author:** Christian Mendieta (with Claude Code)

## Goal

Let the user generate, review, and publish blog posts directly from Claude
Desktop by exposing the existing LangGraph blog pipeline through a remote MCP
server. The user's laptop should run nothing but Claude Desktop; everything else
is remote.

## Constraints & Decisions

These were settled during brainstorming and drive the rest of the design:

1. **Client + hosting:** Claude Desktop connects to a **hosted remote MCP
   server** over **streamable-HTTP**, added as a custom connector. No local
   process on the laptop.
2. **Single deployment:** The MCP server **mounts into the existing FastAPI
   app** as an ASGI sub-application. Same process, event loop, DB session
   factory, and background worker. No second service.
3. **Direct domain calls:** MCP tools call the domain layer in-process (the
   `Job`/`Settings` SQLAlchemy models, `agentic.graph.create_blog_graph`,
   `agentic.nodes.publisher.publisher_node`) — **not** the app's own REST
   endpoints over HTTP. No internal network hop, no cookie-JWT reuse.
4. **Auth = managed OAuth provider.** Claude Desktop's remote connector requires
   OAuth 2.1 (discovery → dynamic client registration → auth-code + PKCE). A
   managed provider owns login, consent, DCR, and token issuance. **Our server
   only verifies tokens.** No authorize/token/PKCE code of our own.
   - **Recommended provider: Stytch** (its "Connected Apps" product is built for
     MCP-server-as-OAuth with DCR). **WorkOS AuthKit** is a drop-in alternative.
     The choice is pluggable via config; no provider SDK is required on our side
     because verification is a standard JWKS check.
   - **Single-language constraint:** verification stays in Python. We do not use
     any provider's Node/Express helpers.
   - This is entirely separate from the existing UI password/JWT, which keeps
     protecting the web app.
5. **Job UX = fire-and-poll.** Generation takes minutes (worker streams ~8
   graph nodes), which exceeds connector/model timeouts. `generate_blog` queues
   the job and returns a `job_id` immediately; `get_job` retrieves progress and
   the finished article.

## Architecture

```
Claude Desktop ──OAuth──▶ [ Managed OAuth provider (Stytch/WorkOS) ]
      │                          issues access token (JWT)
      │ streamable-HTTP + Bearer token
      ▼
┌──────────────────────────────────────────────────┐
│  Remote FastAPI deployment (single process)        │
│                                                    │
│  /mcp        ← MCP server (token-verified)          │
│                tools call DB + graph IN-PROCESS     │
│  /jobs /settings /auth  ← existing REST API          │
│  background worker (polls pending jobs)  [unchanged]│
│         │                                          │
│         ▼  Postgres (Job, Settings)                 │
└──────────────────────────────────────────────────┘
```

### New/changed modules

- **`api/mcp_server.py`** (new): builds the MCP server (MCP Python SDK /
  FastMCP), defines the tools, exposes `streamable_http_app()` for mounting.
  Tools call the domain layer directly.
- **`api/mcp_auth.py`** (new): `TokenVerifier` implementation (validate JWT
  against provider JWKS, check issuer + audience) and `AuthSettings` wiring so
  the SDK serves protected-resource metadata and enforces auth.
- **`api/main.py`** (changed): mount the MCP ASGI app; integrate its
  `session_manager` into the existing lifespan; read new OAuth env vars.
- **`requirements.txt`** (changed): add the `mcp` Python SDK.
- **`.env.example`** (changed): add `OAUTH_ISSUER`, `OAUTH_AUDIENCE` (resource
  URL), `OAUTH_JWKS_URL`.

Keeping tools and auth in separate modules from the REST routers preserves clear
responsibility boundaries.

## Tool Catalog

Thin wrappers over existing operations. All tools require a valid token.

| Tool | Args | Returns | Backed by |
|---|---|---|---|
| `generate_blog` | `topic`, `tone?`, `word_count?`, `instructions?` | `{job_id, status}` | insert `Job(status="pending")`; worker picks it up |
| `get_job` | `job_id` | curated job incl. content when completed | `Job` row |
| `list_jobs` | `limit?` | recent jobs, newest first | `Job` query |
| `get_job_logs` | `job_id` | captured log text | `Job.logs` |
| `publish_blog` | `job_id` | `{url, post_id}` | `publisher_node(job.result)` |
| `retry_blog` | `job_id` | new `{job_id, status}` | re-queue failed job |
| `get_settings` | — | current settings | `Settings` row |
| `update_settings` | `default_tone?`, `default_word_count?`, `llm_temperature?`, `llm_model?`, `auto_publish_to_ghost?` | updated settings | `Settings` row |

**Deferred (YAGNI, destructive from chat):** `delete_job`. Easy to add later.

### `get_job` curated response

`Job.result` is a large JSONB of the final pipeline state. `get_job` returns a
curated subset so the article is readable in Claude and review is first-class:

```
get_job(job_id) → {
  id, topic, status, current_node,   // progress
  error,                             // present when failed
  result: {                          // present once completed
    final_content,                   // full article Markdown — for review
    seo_title, seo_description, tags,
    word_count,
    warnings                         // e.g. force-published / fact-check notes
  }
}
```

## Data Flow

Primary flow — **review before publish**:

1. **`generate_blog`** — open async DB session, insert `Job(status="pending")`,
   defaulting `tone`/`word_count` from the `Settings` row (same as the existing
   `create_job`). Return `{job_id, status}`.
2. **worker (unchanged)** — polls pending jobs, sets `running`, streams
   `create_blog_graph()`, writes `result` + `logs`, sets `completed`/`failed`.
3. **`get_job`** — read the row, return curated result; Claude shows the draft
   for the user to read.
4. **`publish_blog`** — guard on `status == "completed"` and non-empty
   `result`; call `publisher_node(job.result)` in-process; on success set
   `status = "published"` and merge publish updates into `result`; return
   `{url, post_id}`.
5. **`retry_blog`** — guard on `status == "failed"`; clone topic/tone/word
   count/instructions into a new `pending` job.

MCP tools and the worker share the single `AsyncSessionLocal`; there is no second
DB path.

## Error Handling

Follows the repo rule: **no silent error swallowing**; every failure is visible.

- **Status/existence guards** mirror the REST semantics as MCP tool errors:
  - unknown `job_id` → "Job not found"
  - `publish_blog` on a non-completed job → "Only completed jobs can be published"
  - `publish_blog` with no result → "Job has no result to publish"
  - `retry_blog` on a non-failed job → rejected with a clear message
- **Ghost publish failure** → return the actual underlying error message from
  `publisher_node` (not a generic string).
- **Worker failures** are already persisted (`status="failed"`, `Job.error`,
  `logs`); `get_job` exposes them so the user can read why and choose
  `retry_blog`.
- **Auth failures** (missing/expired/bad-signature/wrong-issuer/wrong-audience)
  → `401` at the transport. The SDK's protected-resource metadata directs
  Claude Desktop to re-authenticate automatically.

## Testing Strategy

- **Unit (tools):** against a test DB with `ENV=test` (existing lifespan skips
  worker autostart in test). Assert `generate_blog` inserts a `pending` row,
  `get_job` curates the result correctly, and `publish_blog`/`retry_blog`
  enforce their status guards. Mock `publisher_node` and the graph.
- **Unit (auth):** token verifier — valid / expired / bad-signature /
  wrong-issuer / wrong-audience, using a locally generated test JWKS.
- **Integration:** drive the tools through the MCP SDK's in-memory client with a
  mock verifier, end-to-end against the test DB.
- **Manual (once):** connect Claude Desktop to the deployed URL and run
  generate → review → publish for real.

## Out of Scope

- `delete_job` and any other destructive tools (deferred).
- Multi-user / per-user data isolation (single-user tool; the OAuth token gates
  the endpoint and tools act as the one user).
- Changes to the LangGraph pipeline, worker, or REST API behavior.
- Self-hosted OAuth authorization server (explicitly rejected in favor of a
  managed provider).

## Manual Setup (documented, not code)

1. Create an application in the OAuth provider (Stytch recommended; WorkOS
   alternative).
2. Enable **dynamic client registration** for the app.
3. Configure `OAUTH_ISSUER`, `OAUTH_AUDIENCE` (the MCP server's resource URL),
   and `OAUTH_JWKS_URL` in the deployment environment.
4. Deploy; add `https://<domain>/mcp` as a custom connector in Claude Desktop
   and complete the one-time sign-in.
