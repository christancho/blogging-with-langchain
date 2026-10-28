# Architecture Reference

Implementation-level reference for extending this codebase — node internals, extension
procedures, state fields, and the SSE log-streaming implementation. For installation,
usage, and end-user docs, see [`README.md`](../README.md); its Architecture and Workflow
Details sections cover the graph shape and each node's behavior and are the source of
truth for the editor's approval criteria specifically.

## Key Files

- `agentic/graph.py`: StateGraph definition, conditional routing logic, and workflow orchestration
- `agentic/state.py`: BlogState TypedDict defining all state fields
- `agentic/config.py`: Configuration management with automatic LLM fallback (Anthropic → OpenRouter)

### Prompt System

Prompts are Jinja2 templates stored in `agentic/prompts/*.txt` and loaded via `PromptLoader` utility:

```python
from agentic.nodes.prompt_loader import PromptLoader

template = PromptLoader.load("writer")
prompt = template.render(
    topic=state["topic"],
    tone=Config.BLOG_TONE,
    research=state["research_summary"],
    # ... other context variables
)
```

`PromptLoader.clear_cache()` clears the cache during development.

## Common Development Tasks

### Adding a New Quality Check
1. Update `agentic/prompts/editor.txt`: add new criteria to the assessment section
2. Update the scoring guide if needed to reflect new criteria weighting
3. Update `agentic/prompts/revision.txt`: include new check in revision guidance
4. Test with sample articles to ensure LLM understands the new criteria
5. Optional: update fallback mechanical checks in `agentic/nodes/editor.py` if adding quantitative metrics
6. Update README's Workflow Details > Editor Node section to keep the documented gating criteria accurate

### Modifying a Prompt
1. Edit the corresponding `.txt` file in `agentic/prompts/`
2. Templates use Jinja2 syntax: `{{ variable }}`, `{% if %}`, etc.
3. Clear cache in development: `PromptLoader.clear_cache()`
4. Test changes with `python main.py "test topic" --debug`

### Adding a New Node
1. Create `agentic/nodes/new_node.py` with function signature: `def new_node(state: BlogState) -> dict`
2. Add to `agentic/nodes/__init__.py`
3. Update workflow in `agentic/graph.py`: `workflow.add_node("new_node", new_node)`
4. Add edges: `workflow.add_edge("previous", "new_node")`
5. Update `agentic/state.py` with new output fields
6. If the node calls an LLM, add an entry to `Config.NODE_LLM_DEFAULTS` and use `Config.get_llm("new_node")`, plus a label in `NODE_LABELS` in `web/app/(dashboard)/settings/page.tsx`

### Per-Node LLM Settings
Each LLM-calling node has an `effort` (`off`/`low`/`medium`/`high`/`xhigh`/`max`) and a `temperature` in `Config.NODE_LLM_DEFAULTS`. `get_llm(node)` checks the model's OpenRouter `supported_parameters` (fetched once per process via `get_model_supported_params()`): it sends `reasoning.effort` when the model supports reasoning and effort isn't `off`, otherwise `temperature` if the model supports it; never both, since thinking and a custom temperature are exclusive. If capabilities are unknown (fetch failed, model not listed) it warns and sends what the node is configured for. The settings page enables the effort/temperature inputs by the same rule, from the flags `/settings/models` returns. Partial overrides live in the `settings.llm_node_settings` JSONB column, are edited via the settings page / REST API / MCP `update_settings`, and the worker copies them into `Config.NODE_LLM_SETTINGS` before each job.

### Changing the Workflow Order
1. Update edges in `agentic/graph.py`: `workflow.add_edge(source, target)`
2. Update conditional routing if needed: `route_editor_decision()`
3. Regenerate visualization: `python main.py --visualize`
4. Update README's Architecture/Workflow Diagram and this file

## Testing Guidelines

### Unit Tests
- Test files mirror source structure: `tests/test_tools.py` tests `agentic/tools/*.py`
- Use pytest fixtures for common setup
- Mock external APIs (Brave, Anthropic, Ghost)
- Test each tool independently

### Golden Tests
Located in `tests/golden_tests/`:
- Store expected outputs for regression testing
- Verify workflow produces consistent results
- Update golden files when intentionally changing output format

### Testing a Workflow Change
1. Add unit tests for new node/tool logic
2. Run full workflow with test topic: `python main.py "test topic"`
3. Verify output in `output/` directory
4. Check all quality checks pass (word count, links, structure)

## State Management

The `BlogState` TypedDict flows through the entire graph. Key principles:

- **Immutable updates**: Nodes return dicts that merge into state
- **Typed fields**: All fields defined in `agentic/state.py` with type hints
- **Optional fields**: Uses `total=False` to allow partial state
- **No direct mutation**: Never modify state in-place

**Critical state fields:**
- `fact_check_status`: `"passed"` / `"failed"` / `"force_passed"`, drives the fact-check loop
- `approval_status`: Controls routing — `"pending"` (initial) → `"approved"`, `"rejected"`, or `"force_publish"`
- `revision_count` / `fact_revision_count`: Track attempts against the editor and fact-check loops independently (each capped at `MAX_REVISIONS`)
- `editor_feedback`: Passed to writer during revisions
- `final_content`: Set once approved, ready for publishing
- `errors` / `warnings`: Accumulate throughout workflow

## API Backend & Live Pipeline Logs

The backend is a FastAPI application with a PostgreSQL database and a background worker for job execution.

**Live log streaming:** Pipeline execution logs stream in real time to the web UI via `GET /jobs/{id}/events` (Server-Sent Events, implemented as `stream_job_events` in `api/routes/jobs.py`). The endpoint:
- Replays completed log lines from `Job.logs` (the durable replay store, written periodically by the existing log-flusher)
- Subscribes to live updates via Postgres LISTEN/NOTIFY on a per-run channel `blog_run_{id}` — subscribing before reading the replay snapshot, so nothing published during setup is lost
- Filters live events to `seq > k` (where `k` is the number of completed lines already covered by the replay) to avoid re-delivering lines the client already has
- Independently polls the job's terminal status every ~2s via a dedicated DB connection, regardless of NOTIFY health — this is what catches the case where the publisher's own DB connection failed at startup and the `done` NOTIFY is never sent
- Closes the stream (`event: done`) when the job reaches a terminal status: `completed`, `failed`, or `published`

**Implementation details:**
- **Publishing:** `api/worker.py`'s `TeeWriter` class emits each completed (newline-terminated) stdout line, tagged with a monotonic `seq`, to an `on_line` callback. In `_run_job`, that callback is `LogPublisher.publish(seq, line)` (`api/log_stream.py`) — a thread-safe, non-blocking enqueue. A dedicated `LogPublisher` thread drains the queue and NOTIFYs each line on `blog_run_{job_id}` via its own psycopg2 connection, so publishing never blocks the pipeline. `LogPublisher.stop(status)` sends a final `done` event.
- **Payload chunking:** `build_payloads(seq, line, max_bytes=7000)` in `api/log_stream.py` serializes each line to JSON for NOTIFY; a line whose serialized size exceeds `max_bytes` is split into character-boundary-safe fragments sharing the same `seq`, with `last: true` on the final fragment so the client can reassemble reliably (not by length).
- **Replay/live seam:** `count_completed_lines(text)` (`api/log_stream.py`) counts newline-terminated lines in `Job.logs` to compute `k`; `Job.logs` itself is unchanged JSON-free plain text (the existing `_start_log_flusher` mechanism), so replay is just that raw text.

**Live queue updates:** The dashboard does not poll. `GET /jobs/stream` (`stream_jobs` in `api/routes/jobs.py`) is an SSE stream of the active (pending/running) jobs: it sends an `event: jobs` snapshot on connect and again whenever the `jobs_changed` Postgres channel fires, with keep-alive comments in between. The channel is fed by the `jobs_changed_notify` trigger (alembic `d7e2a9c41f60`; mirrored in `api/models.py` for `create_all`), which fires on job insert, delete, and `status`/`current_node` updates — so every writer (REST routes, MCP tools, worker) is covered without application code, while the worker's 2-second `logs` flushes do not fire it. On the web side, `app/(dashboard)/layout.tsx` opens the one subscription (`subscribeActiveJobs` in `web/lib/api.ts`) and shares it via `ActiveJobsContext` (`web/lib/activeJobs.ts`) with the nav badge and the queue page; a rejected stream re-checks the session and either redirects to `/login` or reconnects.

**Key files:**
- `api/routes/jobs.py`: `stream_job_events` — the `/jobs/{id}/events` SSE endpoint (replay, live forwarding, terminal-status fallback)
- `api/log_stream.py`: `channel_for`, `build_payloads`, `count_completed_lines`, `done_payload`, and the `LogPublisher` thread (NOTIFY publishing)
- `api/worker.py`: `TeeWriter` (captures pipeline stdout, tags lines with `seq`, invokes the `on_line` callback) and `_run_job` (wires `TeeWriter` to a `LogPublisher`)
- `api/pg_dsn.py`: `plain_dsn()` — strips the SQLAlchemy `+driver` suffix so raw psycopg2/asyncpg connections can use `DATABASE_URL`
- `web/lib/api.ts`: `streamJobEvents`/`parseEvent` — the browser `EventSource` client, including fragment reassembly by the `last` flag
- `web/app/(dashboard)/queue/page.tsx`: `LogPanel` — the live log viewer consuming the SSE stream

## Debugging Tips

- `python main.py "topic" --debug` shows detailed error traces and execution flow
- `SAVE_INTERMEDIATE_OUTPUTS=true` in `.env` saves state after each node execution
- LangSmith traces (see README's LangSmith Tracing section for setup) are the fastest way to see the exact prompt sent to the LLM, the full response, and which node is failing — check there before reading logs when a node's output looks wrong
- If LLM-based editor evaluation itself fails (not the article), the system falls back to mechanical checks only — check for that fallback before assuming the editor logic is broken
