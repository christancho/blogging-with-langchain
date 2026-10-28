# Session Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `session_notes` input (MCP, REST, web) that the writer uses as the primary source of the post, and brace-escape `instructions` and `session_notes` everywhere they're rendered into a `ChatPromptTemplate`.

**Architecture:** `session_notes` is a nullable `Job` column that the worker copies into `BlogState`. Research fetches URLs from the notes and passes the notes to query generation as a template variable. The writer renders the full escaped notes into `writer.txt`/`revision.txt` behind `{% if session_notes %}`, with a widened grounding rule and a conflict rule. No new nodes, no new LLM calls.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy (async) + Alembic, LangGraph/LangChain (`ChatPromptTemplate`), Jinja2 prompts, FastMCP, Next.js/TypeScript + Jest, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-10-28-session-notes-design.md`

## Global Constraints

- Branch: `feature/105-session-notes` (already created from `origin/dev`). Conventional commits, no emojis, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't push.
- Field name is `session_notes` everywhere (Python, DB column, JSON, TS). TS state variable is `sessionNotes`.
- Escape pattern, inline, matching existing code: `x.replace("{", "{{").replace("}", "}}")`. Escape only the copy passed to `.render(...)`. Never escape values passed as `invoke({...})` variables.
- With no notes (`None`, `""` or whitespace only), behavior is the same as today.
- No new LLM calls and no new nodes. Audience, SEO and editor never receive `session_notes`.
- No silent `except`. Every caught error is printed (CLAUDE.md, learned rule 2).
- Docstrings on all new/changed functions. Use `print`, not `logging`, for pipeline feedback.
- Migration: new revision with `down_revision = 'd7e2a9c41f60'`.
- MCP `generate_blog` docstring and writer-prompt block: copy verbatim from spec §2 and §7.

## Review Focus

1. **Notes containing braces** (`{"a": 1}`, `${VAR}`, `f() { echo hi; }`) must come out literally in the writer's final system message on both the initial and revision paths. Covered in Task 5.
2. **Nodes catch LLM exceptions and keep going.** A brace `KeyError` would be *swallowed* into `errors`, not raised, so "the test didn't crash" proves nothing. Escaping tests must assert the fake LLM was actually called and received the literal text. Covered in Tasks 3 and 5.
3. **Whitespace-only notes** from the web form or MCP must behave as "no notes": no session block and unchanged grounding text. Covered in Tasks 2 and 5.
4. **Retry on both paths** (MCP `retry_blog_impl` and REST `/jobs/{id}/retry`) must carry `session_notes`, or a retried hands-on post silently becomes a generic one. Covered in Task 1.
5. **A URL in both `instructions` and `session_notes`** is fetched once. Covered in Task 4.

---

### Task 1: Storage, MCP and REST input

**Files:**
- Modify: `api/models.py` (`Job`, next to `instructions` at line 18)
- Create: `api/alembic/versions/e4b8c2d1a9f3_add_session_notes_to_jobs.py`
- Modify: `api/mcp_server.py` (`generate_blog_impl` ~line 62, `retry_blog_impl` ~line 220, `generate_blog` tool ~line 326)
- Modify: `api/routes/jobs.py` (`JobCreate` line 27, `_serialize` line 34, `create_job` ~line 68, `retry_job` ~line 309)
- Test: `tests/api/test_mcp_tools.py`, `tests/api/test_jobs.py`

**Interfaces:**
- Produces: `Job.session_notes: Mapped[str | None]`. `generate_blog_impl(session_factory, topic, tone=None, word_count=None, instructions=None, session_notes=None) -> dict`. MCP tool `generate_blog(topic, tone=None, word_count=None, instructions=None, session_notes=None)`. REST `JobCreate.session_notes: str | None = None`. Serialized job dict has key `"session_notes"`.

- [ ] **Step 1: Write failing tests**

In `tests/api/test_mcp_tools.py` (import `retry_blog_impl` if it isn't already imported):
```python
async def test_generate_blog_stores_session_notes(session_factory, seeded_settings):
    out = await generate_blog_impl(session_factory, topic="Coolify setup", session_notes="## Goal\nDeploy {app}")
    async with session_factory() as db:
        job = await db.get(Job, uuid.UUID(out["job_id"]))
        assert job.session_notes == "## Goal\nDeploy {app}"

async def test_generate_blog_session_notes_default_none(session_factory, seeded_settings):
    out = await generate_blog_impl(session_factory, topic="X")
    async with session_factory() as db:
        assert (await db.get(Job, uuid.UUID(out["job_id"]))).session_notes is None

async def test_retry_copies_session_notes(session_factory, seeded_settings):
    # Failed job with instructions="i" and session_notes="notes", then retry_blog_impl.
    # Assert new_job.session_notes == "notes" and new_job.instructions == "i".
```
In `tests/api/test_jobs.py`:
```python
async def test_create_job_with_session_notes(authed_client, seeded_settings):
    resp = await authed_client.post("/jobs", json={"topic": "T", "session_notes": "steps ${X}"})
    assert resp.status_code == 201
    assert resp.json()["session_notes"] == "steps ${X}"

async def test_retry_job_copies_session_notes(authed_client, db, seeded_settings):
    # Failed Job with session_notes="notes", POST /jobs/{id}/retry,
    # assert response json["session_notes"] == "notes".
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/api/test_mcp_tools.py tests/api/test_jobs.py -k session_notes -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'session_notes'` / `AttributeError` / `KeyError`)

- [ ] **Step 3: Implement**

- `Job.session_notes = mapped_column(Text, nullable=True)`.
- Migration `e4b8c2d1a9f3`: `op.add_column('jobs', sa.Column('session_notes', sa.Text(), nullable=True))` on upgrade, `op.drop_column('jobs', 'session_notes')` on downgrade. Header style follows `d7e2a9c41f60_notify_jobs_changed.py`.
- MCP impl, both retries, REST create and serializer: pass/copy `session_notes` next to `instructions`. Update the docstrings' Args.
- MCP tool: add the `session_notes` param, and replace the docstring with the spec §2 text verbatim.

- [ ] **Step 4: Run tests**

Run: `pytest tests/api/test_mcp_tools.py tests/api/test_jobs.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/models.py api/alembic/versions/e4b8c2d1a9f3_add_session_notes_to_jobs.py api/mcp_server.py api/routes/jobs.py tests/api/test_mcp_tools.py tests/api/test_jobs.py
git commit -m "feat: accept session_notes on MCP and REST job creation (#105)"
```

---

### Task 2: Worker and state

**Files:**
- Modify: `agentic/state.py` (after `instructions`, line 19)
- Modify: `api/worker.py` (read ~line 128; run header ~line 205; `initial_state` ~line 218)
- Test: `tests/api/test_worker.py`

**Interfaces:**
- Consumes: `Job.session_notes` (Task 1).
- Produces: `BlogState.session_notes: Optional[str]`. `initial_state["session_notes"]` is always a `str` (stripped, `""` when absent).

- [ ] **Step 1: Write failing tests**

```python
async def test_run_job_passes_session_notes_to_graph(db, seeded_settings):
    # Job(..., session_notes="  ## Goal\nShip it  \n"), mock graph as in existing tests.
    # assert mock_graph.stream.call_args[0][0]["session_notes"] == "## Goal\nShip it"

async def test_run_job_whitespace_session_notes_become_empty(db, seeded_settings):
    # Job(..., session_notes="   \n "), assert initial_state["session_notes"] == ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/api/test_worker.py -k session_notes -v`
Expected: FAIL (`KeyError: 'session_notes'`)

- [ ] **Step 3: Implement**

- State field with comment `# Author's hands-on session brief — the post's foundation (optional)`.
- Worker: `session_notes = (job.session_notes or "").strip()`. Add a header line printing `Session notes:     {len(session_notes):,} chars` or `(none)` when empty, aligned with the existing `Instructions:` line. Add the key to `initial_state`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/api/test_worker.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agentic/state.py api/worker.py tests/api/test_worker.py
git commit -m "feat: pass session_notes from job into workflow state (#105)"
```

---

### Task 3: Brace-escape `instructions` in audience, SEO and editor

**Files:**
- Modify: `agentic/nodes/audience_analysis.py:41`, `agentic/nodes/seo.py:51`, `agentic/nodes/editor.py:65`
- Create: `tests/test_prompt_escaping.py`

**Interfaces:**
- Produces: `tests/test_prompt_escaping.py::CapturingLLM` helper (used again in Task 5).

- [ ] **Step 1: Write failing tests**

The helper records the messages the chain actually sends, so a `KeyError` swallowed by a node shows up as "never called":
```python
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessage

BRACES = 'Use ${POSTGRES_PASSWORD} and {"a": 1} and f() { echo hi; }'

class CapturingLLM:
    """Stand-in for Config.get_llm(): records prompt messages, returns a canned reply."""
    def __init__(self, reply="ok"):
        self.calls = []
        self.reply = reply
    def __call__(self, *args, **kwargs):
        def _run(prompt_value):
            self.calls.append("\n".join(m.content for m in prompt_value.to_messages()))
            return AIMessage(content=self.reply)
        return RunnableLambda(_run)
```
One test per node: patch `agentic.nodes.<node>.Config.get_llm` with a `CapturingLLM`, then call the node with minimal state. The state includes `instructions=BRACES`, and for SEO and editor, `article_content`/`formatted_content`. Assert:
```python
assert llm.calls, "LLM never invoked — prompt construction failed"
assert BRACES in llm.calls[0]
```
Names: `test_audience_analysis_escapes_instructions`, `test_seo_escapes_instructions`, `test_editor_escapes_instructions`. Editor runs `ContentAnalysisTool` first, so give it a short article. If its reply parsing fails afterward, that's fine: the assertions only cover the captured prompt.

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_prompt_escaping.py -v`
Expected: 3 FAIL on `LLM never invoked`

- [ ] **Step 3: Implement**

In each node, before `render`: `instructions_escaped = instructions.replace("{", "{{").replace("}", "}}")`, then pass `instructions=instructions_escaped` (audience: escape the value after the `or "No specific instructions provided."` fallback). Keep the `print`s on the raw value.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prompt_escaping.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add agentic/nodes/audience_analysis.py agentic/nodes/seo.py agentic/nodes/editor.py tests/test_prompt_escaping.py
git commit -m "fix: escape braces in instructions before ChatPromptTemplate (#105)"
```

---

### Task 4: Research uses session notes

**Files:**
- Modify: `agentic/tools/query_generator.py` (`generate_queries`, lines 17-70)
- Modify: `agentic/nodes/research.py` (Step 1 lines 51-67, Step 2 lines 72-76)
- Test: `tests/test_deep_research_tools.py` (query generator), `tests/test_research_session_notes.py` (create, node)

**Interfaces:**
- Consumes: `state["session_notes"]` (Task 2).
- Produces: `QueryGeneratorTool.generate_queries(topic: str, instructions: str = "", num_queries: int = 6, session_notes: str = "") -> List[str]`.

- [ ] **Step 1: Write failing tests**

Query generator (patch `agentic.tools.query_generator.Config.get_llm` with `CapturingLLM(reply="q1\nq2")` from `tests/test_prompt_escaping.py`):
```python
def test_session_notes_in_query_prompt():
    # generate_queries("Coolify", session_notes='Ran `docker compose up` with {"x": 1}', num_queries=2)
    assert "Author's Session Notes" in llm.calls[0]
    assert '{"x": 1}' in llm.calls[0]

def test_no_session_section_without_notes():
    # generate_queries("Coolify", num_queries=2)
    assert "Author's Session Notes" not in llm.calls[0]
```
Research node (`tests/test_research_session_notes.py`): patch `agentic.tools.BraveSearchTool`, `URLFetcherTool`, `QueryGeneratorTool`, `ContentSynthesisTool` and `LinkValidatorTool` with MagicMocks. Make `url_fetcher.extract_urls_from_text` the real function: `URLFetcherTool.extract_urls_from_text` (check whether it's a static/instance method and bind accordingly). `validate_urls` returns `(urls, [])`. The search returns `'{"results": []}'`. The synthesizer returns `{"summary": "", "key_facts": []}`.
```python
def test_research_fetches_session_note_urls():
    # state: topic, instructions="see https://a.example/doc", session_notes="used https://b.example/x and https://a.example/doc"
    fetched = [c.args[0] for c in url_fetcher.fetch_url_content.call_args_list]
    assert sorted(fetched) == ["https://a.example/doc", "https://b.example/x"]  # deduped

def test_research_passes_session_notes_to_query_generator():
    assert query_generator.generate_queries.call_args.kwargs["session_notes"] == state["session_notes"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_deep_research_tools.py tests/test_research_session_notes.py -k "session" -v`
Expected: FAIL

- [ ] **Step 3: Implement**

- Query generator: add `{session_notes_section}` to the system prompt right after `{instructions_section}`. When `session_notes` is non-empty, its value is the spec §6 text verbatim with the notes substituted via Python f-string *before* invoke (it's passed as a variable value, so no escaping). Otherwise it's `""`. Add it to `invoke({...})`.
- Research node: `session_notes = state.get("session_notes", "") or ""`. Run Step 1 when `instructions or session_notes`, using URLs from both, de-duplicated with order kept (`dict.fromkeys`). Print `📎 Found N priority URLs from instructions/session notes`. Step 2: pass `session_notes=session_notes` as a keyword. The fallback query list is unchanged.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_deep_research_tools.py tests/test_research_session_notes.py -v`
Expected: all PASS (pre-existing tests that need API keys may skip, as before)

- [ ] **Step 5: Commit**

```bash
git add agentic/tools/query_generator.py agentic/nodes/research.py tests/test_deep_research_tools.py tests/test_research_session_notes.py
git commit -m "feat: drive research queries and priority URLs from session notes (#105)"
```

---

### Task 5: Writer uses session notes as the foundation

**Files:**
- Modify: `agentic/prompts/writer.txt` (after Custom Instructions block line 13; FACTUAL GROUNDING block lines 174-180)
- Modify: `agentic/prompts/revision.txt` (near VERIFIED FACTS line 29; FACTUAL GROUNDING lines 115-117)
- Modify: `agentic/nodes/writer.py` (line 31 escaping; revision render ~line 87; initial render ~line 125)
- Test: `tests/test_writer_prompt.py`, `tests/test_prompt_escaping.py`

**Interfaces:**
- Consumes: `state["session_notes"]` (Task 2), `CapturingLLM`/`BRACES` (Task 3).
- Produces: `writer.txt` and `revision.txt` accept a `session_notes` render variable (default undefined/empty means the block is omitted).

- [ ] **Step 1: Write failing tests**

`tests/test_writer_prompt.py`, new class `TestSessionNotesBlock`, run against both `writer` (`MINIMAL_WRITER_ARGS`) and `revision` (`MINIMAL_REVISION_ARGS`) via `pytest.mark.parametrize`:
```python
def test_block_rendered_with_notes(name, args):
    r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS, session_notes="I ran X")
    assert "AUTHOR'S SESSION NOTES" in r and "I ran X" in r
    assert "or to the AUTHOR'S SESSION NOTES" in r
    assert "the VERIFIED FACT wins" in r

def test_no_block_without_notes(name, args):
    r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS, session_notes="")
    assert "AUTHOR'S SESSION NOTES" not in r
    assert "must trace back to one of the numbered VERIFIED FACTS above" in r

def test_grounding_unchanged_without_notes(name, args):
    # Render WITHOUT passing session_notes at all (undefined variable path)
    r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS)
    assert "use ONLY what is in the VERIFIED FACTS list" in r
    assert "SESSION NOTES" not in r and "first person" not in r
```
`tests/test_prompt_escaping.py`:
```python
def test_writer_initial_escapes_notes_and_instructions():
    # patch agentic.nodes.writer.Config.get_llm with CapturingLLM(reply=<~50-word markdown article>)
    # state: topic, instructions=BRACES, session_notes=BRACES, research_summary="r", no editor feedback
    assert llm.calls and llm.calls[0].count(BRACES) == 2

def test_writer_revision_escapes_notes():
    # state with approval_feedback/article_content set so the node takes the revision branch
    # (mirror the branch condition at writer.py:~60), session_notes=BRACES
    assert llm.calls and BRACES in llm.calls[0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_writer_prompt.py tests/test_prompt_escaping.py -v`
Expected: new tests FAIL

- [ ] **Step 3: Implement**

- Both templates: insert the `{% if session_notes %}…{% endif %}` block from spec §7 verbatim. In `writer.txt`, put it right after the Custom Instructions block. In `revision.txt`, put it right before the VERIFIED FACTS block.
- Grounding blocks in both templates: keep the existing first bullet as is in an `{% else %}`. Under `{% if session_notes %}`, use the two spec §7 sentences verbatim, keeping the existing "Do not assert specific technical details from your training knowledge" and hedge bullets, reworded to "VERIFIED FACTS list or session notes".
- `writer.py`: `session_notes = state.get("session_notes", "") or ""`. Create `session_notes_escaped` and `instructions_escaped` with the inline pattern. Pass `session_notes=session_notes_escaped` to both renders and `instructions=instructions_escaped` to the initial render. In the initial-mode header, print `Session notes: {len(session_notes):,} characters`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_writer_prompt.py tests/test_prompt_escaping.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agentic/prompts/writer.txt agentic/prompts/revision.txt agentic/nodes/writer.py tests/test_writer_prompt.py tests/test_prompt_escaping.py
git commit -m "feat: writer builds the post on session notes with widened grounding (#105)"
```

---

### Task 6: Web UI field

**Files:**
- Modify: `web/lib/api.ts` (`Job` ~line 12, `JobCreate` ~line 30)
- Modify: `web/app/(dashboard)/new-post/page.tsx` (state ~line 21, submit ~line 60, textarea after line ~143)
- Modify: `web/lib/__tests__/activeJobs.test.ts` (fixture line 8), plus any other `Job` fixture `tsc` flags

**Interfaces:**
- Consumes: REST `session_notes` (Task 1).

- [ ] **Step 1: Add the types and update fixtures** with `session_notes: null`.

- [ ] **Step 2: Add the textarea**

`const [sessionNotes, setSessionNotes] = useState('')`. Add a second `<div>` after the instructions textarea, using the label/hint copy from spec §4 verbatim (the hint is the `placeholder`), `rows={10}`, and the same classes as the instructions textarea except `resize-y` instead of `resize-none`. Submit body: `session_notes: sessionNotes || undefined`.

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit && npm test`
Expected: no type errors, all tests PASS

- [ ] **Step 4: Commit**

```bash
git add web/lib/api.ts "web/app/(dashboard)/new-post/page.tsx" web/lib/__tests__
git commit -m "feat: add session notes field to new-post form (#105)"
```

---

### Task 7: Full-suite, container and real-run verification

**Files:** none, unless a check fails.

- [ ] **Step 1: Full test suite**

Run: `pytest -q`
Expected: no failures, apart from any already failing on `origin/dev`. Run the same command on `origin/dev` to compare if anything fails.

- [ ] **Step 2: Migration and container check (learned rule 6)**

Run: `docker compose up -d --build`, then poll `docker compose ps` until the API service shows `healthy`. Then `docker compose exec <api-service> alembic downgrade -1 && docker compose exec <api-service> alembic upgrade head`.
Expected: healthy, downgrade and upgrade both succeed, `\d jobs` shows `session_notes text`.

- [ ] **Step 3: Real-run check (learned rule 1)**

Against the local stack, create a job through the MCP `generate_blog_impl` path (or `POST /jobs`). Use a genuine 1–3k-word session brief that includes a docker-compose snippet and a JSON config, and real API keys from `.env`. Wait for completion and read the article. Confirm and report each item with quotes from the article:
1. It follows the session's order of events, in first person.
2. A command and a config block from the notes appear exactly.
3. The job logs show `Session notes: N chars`, priority URLs from the notes being fetched, and research queries that relate to the session.
4. There's no `KeyError`/`missing variables` anywhere in the logs.

If the article fails 1 or 2, stop and report to the user. That's a prompt-design question, not something to fix inline.

- [ ] **Step 4: Report** results to the user. Don't push or open a PR without their go-ahead.
