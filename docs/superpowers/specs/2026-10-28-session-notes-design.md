# Session Notes Design

**Issue:** #105 — Add session notes input as the foundation for hands-on posts

## Problem

Most posts start as hands-on sessions with an AI assistant (Claude, ChatGPT, ...) that run from idea to deployment. At the end of the session the user says "generate a blog post with this", and the chat AI calls the MCP `generate_blog` tool. Today the only place to put the session is `instructions`, which doesn't work for this:

- **Research never treats it as source material.** Only URLs are taken from `instructions` and it steers query generation (`agentic/nodes/research.py:52-75`). Nothing in it becomes a fact.
- **The writer's grounding rule suppresses it.** `writer.txt` requires every specific claim (versions, commands, config) to trace back to the numbered VERIFIED FACTS list. Commands and config from the session aren't in that list, so they get omitted or hedged, and those are the most valuable parts of a hands-on post.
- **`instructions` is meant for directives.** Session content in that slot is read as orders to the writer rather than as material.

There's also a latent bug: `instructions` is rendered into prompts **unescaped** in four nodes, and the result is passed to `ChatPromptTemplate`, which treats `{...}` as template variables. Any brace in `instructions` (JSON, YAML, `${VAR}`) crashes the node:

```
KeyError: Input to ChatPromptTemplate is missing variables {'"a"', 'POSTGRES_PASSWORD'}
```

(Reproduced against the `seo` prompt with `instructions='... ${POSTGRES_PASSWORD} and {"a": 1}'`.) Session notes are full of braces, so they'd hit this on almost every real session.

## Decisions

| Question | Decision |
|---|---|
| Role of the session | **The foundation of the post.** The article builds on and around it. |
| Input form | **Free-form markdown** in one `session_notes` field. The MCP tool description suggests a structure but doesn't require it. |
| Who condenses the session | **The chat AI**, before calling MCP. The pipeline gets a detailed brief (typically 2–5k words), not a raw transcript. |
| Second condensing pass in the pipeline | **None.** The writer gets the notes in full. Condensing them into facts would lose the reasoning, the order of attempts and the dead ends, and it would add an LLM call that can paraphrase commands. |
| Web research | **Supports the session.** Queries are generated from the notes, and URLs in the notes are fetched first. |
| Voice | **First person, AI mentioned where it matters.** |
| Notes vs. web conflict | **Web wins.** The fact checker is unchanged: contradicted claims are corrected from sources, and the user reviews before publishing. |
| Entry points | **MCP, REST and web UI**, kept consistent. |
| `instructions` escaping | **Fixed in this change.** |

## Approach

`session_notes` is a new optional input that flows MCP/REST/web → `Job` row → worker → `BlogState` → research and writer. The writer is the only node that reads the full notes, and it treats them as the primary source. The grounding rule is widened to accept the notes, and a conflict rule keeps fact-checker corrections authoritative.

With no `session_notes` (missing, empty or whitespace only), behavior is the same as today. The one exception is the `instructions` brace fix, which only changes inputs that currently crash.

No new nodes, no new LLM calls.

## Changes

### 1. Storage: `api/models.py` + migration

- `Job.session_notes: Mapped[str | None] = mapped_column(Text, nullable=True)`, next to `instructions`.
- New Alembic revision with `down_revision = 'd7e2a9c41f60'`: `add_column('jobs', 'session_notes', Text, nullable=True)`, and `drop_column` on downgrade.

### 2. MCP: `api/mcp_server.py`

- `generate_blog_impl(session_factory, topic, tone=None, word_count=None, instructions=None, session_notes=None)` stores `session_notes` on the new `Job`.
- `retry_blog_impl` copies `session_notes=original.session_notes`, as it does for `instructions`.
- The `generate_blog` tool gets `session_notes: str | None = None`. The tool docstring is what the chat AI reads, so it carries the guidance:

  > Queue a new blog-generation job. Returns a job_id to poll with get_job.
  >
  > `instructions`: short directives for the post (audience, focus, angle).
  >
  > `session_notes`: when the user has worked through something hands-on in this conversation (setup, experiment, build, deployment) and wants a post about it, pass a detailed markdown account of the session. It becomes the foundation of the post. Include: the goal; the steps in the order they happened; exact commands, config and code that worked; errors hit and how they were fixed; dead ends worth mentioning; lessons learned; links used. Write it from the user's point of view and note where the AI's suggestions helped or failed. Remove secrets (API keys, tokens, passwords, private hostnames). Prefer completeness over brevity.

- `get_job_impl` is unchanged. It doesn't echo the notes back, because the calling chat already has them.

### 3. REST: `api/routes/jobs.py`

- `JobCreate.session_notes: str | None = None`; `create_job` stores it.
- `_serialize` adds `"session_notes": job.session_notes` next to `instructions`.
- `retry_job` copies `session_notes=original.session_notes`.

### 4. Web: `web/lib/api.ts`, `web/app/(dashboard)/new-post/page.tsx`

- `api.ts`: `Job.session_notes: string | null`; `JobCreate.session_notes?: string`.
- `new-post/page.tsx`: a `sessionNotes` state and a second optional textarea under "Custom instructions":
  - Label: **Session notes** *(optional)*
  - Hint: "Paste a hands-on session summary: steps, commands, errors and fixes, lessons. It becomes the foundation of the post."
  - `rows={10}`, vertically resizable (`resize-y`), otherwise the same styling as the instructions textarea.
  - Sent as `session_notes: sessionNotes || undefined`, the same pattern as `instructions`.
- Update `web/lib/__tests__` fixtures that build a `Job` (for example `activeJobs.test.ts`) with `session_notes: null`.

### 5. Worker and state: `api/worker.py`, `agentic/state.py`

- `BlogState.session_notes: Optional[str]  # Author's hands-on session brief — the post's foundation (optional)`.
- Worker reads `session_notes = (job.session_notes or "").strip()` next to `instructions`, puts it in `initial_state["session_notes"]`, and prints its length in the run header, for example `Session notes: 14,230 chars` or `(none)`, so oversized inputs show up in the job logs.

### 6. Research: `agentic/nodes/research.py`, `agentic/tools/query_generator.py`

Only active when `session_notes` is non-empty.

- **Priority URLs:** Step 1 extracts URLs from `instructions` **and** `session_notes`, de-duplicated, then validates and fetches them on the existing path. Failed fetches are logged and skipped, as today.
- **Queries:** `QueryGeneratorTool.generate_queries(topic, instructions="", num_queries=6, session_notes="")`. When notes are present, the system prompt gets a section:

  > **Author's Session Notes** (the article is built on this hands-on session): {session_notes}
  >
  > Generate queries that support this session: official documentation for the tools and versions used, known issues behind the errors encountered, current best practices for the steps taken. Don't research the topic in the abstract.

  The notes are passed as a template **variable** (`{session_notes_section}`), like `instructions_section` today. Variable values aren't re-parsed by LangChain, so no escaping is needed here.

### 7. Writer: `agentic/nodes/writer.py`, `agentic/prompts/writer.txt`, `agentic/prompts/revision.txt`

- `writer.py` reads `session_notes = state.get("session_notes", "") or ""`, escapes it (see section 8) and passes it to **both** the initial `writer` render and the `revision` render, so revisions keep the source.
- `writer.txt` and `revision.txt` get a block that renders only when notes are present:

  ```
  {% if session_notes %}
  **AUTHOR'S SESSION NOTES — Primary Source (the foundation of this article):**
  {{ session_notes }}

  **How to use the session notes:**
  - This hands-on session is the foundation of the article. Build on it and around it: follow its order of events, from idea to outcome.
  - Write in first person as the author ("I set up…", "my first attempt failed…").
  - Mention the AI assistant where it shaped the story (a suggestion that worked, one that broke something). Don't hide it and don't make it the theme.
  - Reproduce commands, configuration, code and error messages exactly as they appear in the notes.
  - Keep instructive dead ends and fixes; they're what makes a hands-on post worth reading.
  - Use web research as supporting context: official docs, current versions, citations.
  {% endif %}
  ```

- **Grounding rule** in `writer.txt` (the `FACTUAL GROUNDING` block) and the equivalent in `revision.txt`. When notes are present, the rule reads:
  - "Every specific claim must trace back to one of the numbered VERIFIED FACTS above **or to the AUTHOR'S SESSION NOTES**."
  - "If a VERIFIED FACT contradicts the session notes, the VERIFIED FACT wins: use the verified information and adjust the narrative to match."

  The conflict rule matters because `fact_checker.py:242-263` adds verified corrections to `research_key_facts`. Without it, a revision would see the notes and the correction disagreeing, with nothing saying which to trust.

  Without notes, the grounding text stays as it is.

### 8. Brace escaping: `instructions` and `session_notes`

Every user-supplied string that's rendered into a Jinja template whose output is then passed to `ChatPromptTemplate.from_messages` as a message must be brace-escaped first, following the existing inline pattern (`x.replace("{", "{{").replace("}", "}}")`):

| Node | Field(s) to escape before render |
|---|---|
| `writer.py` | `instructions` (initial render), `session_notes` (initial and revision renders) |
| `audience_analysis.py` | `instructions` |
| `seo.py` | `instructions` |
| `editor.py` | `instructions` |

Escape only the copy passed to `render(...)`. Log `print`s keep the raw value. Strings passed as `invoke({...})` variables (the query generator) aren't escaped.

## Unchanged

- Fact checker, formatter, publisher: no changes.
- Audience, SEO and editor don't get the session notes. They work from the article, which already carries the story, and this keeps token cost down. They only get the `instructions` escaping fix.
- No size cap on `session_notes`. Its length is logged.

## Error handling

- Empty or whitespace-only notes are treated as absent (the worker strips them, and the templates use `{% if session_notes %}`).
- URL fetch failures from the notes are logged and skipped, on the existing path.
- No new LLM calls, so no new LLM failure modes.

## Testing

- `tests/test_writer_prompt.py`
  - The session block and the changed grounding/conflict rules render only when notes are present, in both `writer` and `revision`.
  - With no notes, the grounding text is unchanged.
  - Notes containing `{"a": 1}`, `${POSTGRES_PASSWORD}` and a bash function `f() { echo hi; }` build a `ChatPromptTemplate` and `invoke({})` without error, on both the initial and revision paths, and the braces come out literally in the final message.
- `instructions` containing braces: for writer, audience_analysis, seo and editor, the rendered and escaped prompt goes through `ChatPromptTemplate(...).invoke({})` without `KeyError`. Each node's LLM call is mocked.
- `tests/api/test_mcp_tools.py`: `generate_blog_impl` stores `session_notes`, and `retry_blog_impl` copies it.
- `tests/api/test_jobs.py`: REST create stores `session_notes`, the response includes it, and retry copies it.
- `tests/api/test_worker.py`: the worker passes the stripped `session_notes` into the initial state; whitespace-only becomes `""`.
- Research (search, fetch and LLM mocked):
  - URLs from `session_notes` are fetched as priority URLs.
  - `generate_queries` gets the notes.
  - The query prompt includes the session section only when notes are present.
- Migration: `alembic upgrade head` and `downgrade -1` run cleanly.
- Web: `npm test` passes with the updated fixtures.
- Per learned rule 6, the Docker image is built and its real CMD (migrations + startup) runs until the healthcheck is healthy, because this change adds a migration.

**Real-run check (learned rule 1):** before the PR, one real job runs through the MCP `generate_blog` tool with a genuine session brief that contains braces (a compose file or JSON config). The article is read to confirm three things:

1. It follows the session's order of events in first person.
2. Commands and config survive exactly.
3. Any fact-checker corrections are applied.

## Out of scope

- Importing raw ChatGPT/Claude export files.
- Showing session notes on the history/preview pages.
- Passing session notes to the editor for a fidelity check.
