# Writer Fact Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the writer node from hallucinating specific factual claims by surfacing the research key facts as a numbered, bounded inventory in both the writer and revision prompts.

**Architecture:** Pass the already-extracted `research_key_facts` list from state into both Jinja2 template renders in `writer.py`. Update `writer.txt` and `revision.txt` to display a numbered fact inventory and an anchoring rule that instructs the LLM to stay within it.

**Tech Stack:** Python, Jinja2 (`Template.render()`), pytest

---

## File Map

| File | Change |
|---|---|
| `tests/test_writer_prompt.py` | **Create** — unit tests for template rendering with/without key facts |
| `agentic/prompts/writer.txt` | **Modify** — add fact inventory block + anchoring rule |
| `agentic/prompts/revision.txt` | **Modify** — same additions |
| `agentic/nodes/writer.py` | **Modify** — pass `research_key_facts` to both template renders |

---

### Task 1: Write failing tests for writer template rendering

**Files:**
- Create: `tests/test_writer_prompt.py`

- [ ] **Step 1: Create the test file**

```python
"""
Tests for writer and revision prompt template rendering with research_key_facts.
"""
import pytest
from agentic.nodes.prompt_loader import PromptLoader


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    PromptLoader.clear_cache()
    yield
    PromptLoader.clear_cache()


SAMPLE_FACTS = [
    {"fact": "Docling achieved 97.9% table accuracy.", "source": "https://example.com/1", "confidence": "high"},
    {"fact": "LlamaParse processes documents in ~6 seconds.", "source": "https://example.com/2", "confidence": "high"},
    {"fact": "Reducto claims 20% higher accuracy.", "source": "https://example.com/3", "confidence": "medium"},
]

MINIMAL_WRITER_ARGS = dict(
    topic="Test Topic",
    tone="informative",
    instructions="No special instructions.",
    research_summary="Some research.",
    audience_analysis="",
    headline_candidates=[],
    word_count_target=3500,
    min_word_count=3325,
    max_word_count=7000,
    current_date="June 02, 2026",
)

MINIMAL_REVISION_ARGS = dict(
    topic="Test Topic",
    article_content="Some article content.",
    editor_feedback="Fix the intro.",
    word_count_target=3500,
    min_word_count=3325,
    max_word_count=7000,
    current_date="June 02, 2026",
)


class TestWriterTemplateFactInventory:
    def test_fact_inventory_rendered_when_facts_provided(self):
        template = PromptLoader.load("writer")
        rendered = template.render(**MINIMAL_WRITER_ARGS, research_key_facts=SAMPLE_FACTS)
        assert "[FACT 1]" in rendered
        assert "[FACT 2]" in rendered
        assert "[FACT 3]" in rendered

    def test_fact_text_appears_in_inventory(self):
        template = PromptLoader.load("writer")
        rendered = template.render(**MINIMAL_WRITER_ARGS, research_key_facts=SAMPLE_FACTS)
        assert "Docling achieved 97.9% table accuracy." in rendered
        assert "LlamaParse processes documents in ~6 seconds." in rendered

    def test_source_appears_in_inventory(self):
        template = PromptLoader.load("writer")
        rendered = template.render(**MINIMAL_WRITER_ARGS, research_key_facts=SAMPLE_FACTS)
        assert "https://example.com/1" in rendered

    def test_anchoring_rule_present_when_facts_provided(self):
        template = PromptLoader.load("writer")
        rendered = template.render(**MINIMAL_WRITER_ARGS, research_key_facts=SAMPLE_FACTS)
        assert "FACTUAL GROUNDING" in rendered

    def test_fact_inventory_absent_when_no_facts(self):
        template = PromptLoader.load("writer")
        rendered = template.render(**MINIMAL_WRITER_ARGS, research_key_facts=[])
        assert "[FACT 1]" not in rendered
        assert "FACTUAL GROUNDING" not in rendered

    def test_template_renders_without_research_key_facts_kwarg(self):
        """Graceful fallback: key not passed at all (old call sites)."""
        template = PromptLoader.load("writer")
        # Should not raise — Jinja2 undefined defaults to empty/falsy
        rendered = template.render(**MINIMAL_WRITER_ARGS)
        assert "[FACT 1]" not in rendered


class TestRevisionTemplateFactInventory:
    def test_fact_inventory_rendered_when_facts_provided(self):
        template = PromptLoader.load("revision")
        rendered = template.render(**MINIMAL_REVISION_ARGS, research_key_facts=SAMPLE_FACTS)
        assert "[FACT 1]" in rendered
        assert "[FACT 2]" in rendered

    def test_anchoring_rule_present_when_facts_provided(self):
        template = PromptLoader.load("revision")
        rendered = template.render(**MINIMAL_REVISION_ARGS, research_key_facts=SAMPLE_FACTS)
        assert "FACTUAL GROUNDING" in rendered

    def test_fact_inventory_absent_when_no_facts(self):
        template = PromptLoader.load("revision")
        rendered = template.render(**MINIMAL_REVISION_ARGS, research_key_facts=[])
        assert "[FACT 1]" not in rendered

    def test_template_renders_without_research_key_facts_kwarg(self):
        template = PromptLoader.load("revision")
        rendered = template.render(**MINIMAL_REVISION_ARGS)
        assert "[FACT 1]" not in rendered
```

- [ ] **Step 2: Run tests to confirm they fail (templates not updated yet)**

```bash
source .venv/bin/activate && pytest tests/test_writer_prompt.py -v --no-header 2>&1 | tail -20
```

Expected: All tests that check for `[FACT 1]` or `FACTUAL GROUNDING` fail with `AssertionError`. Tests checking absence (`not in`) will pass.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_writer_prompt.py
git commit -m "test: add failing tests for writer fact inventory rendering"
```

---

### Task 2: Update writer.txt — add fact inventory block and anchoring rule

**Files:**
- Modify: `agentic/prompts/writer.txt`

The `writer.txt` file has these sections in order:
1. System preamble
2. `**Research Context:**` — `{{ research_summary }}`
3. `{% if audience_analysis %}` block
4. `{% if headline_candidates %}` block
5. `**Article Requirements:**` ...
6. `**IMPORTANT:**` block ending with `Write the complete article now.`

You will add **Block A** after the `**Research Context:**` section, and **Block B** inside the `**IMPORTANT:**` block before the final line.

- [ ] **Step 1: Add Block A — fact inventory — after the Research Context section**

Find this text in `agentic/prompts/writer.txt`:
```
**Research Context:**
{{ research_summary }}

{% if audience_analysis %}
```

Replace with:
```
**Research Context:**
{{ research_summary }}

{% if research_key_facts %}
**VERIFIED FACTS — Numbered Reference List:**
These facts were sourced and verified during research. Use them as your factual foundation when making specific claims.

{% for fact in research_key_facts %}
[FACT {{ loop.index }}] {{ fact.fact }}
  Source: {{ fact.source }}
  Confidence: {{ fact.get('confidence', 'medium') }}

{% endfor %}
{% endif %}

{% if audience_analysis %}
```

- [ ] **Step 2: Add Block B — anchoring rule — inside the IMPORTANT block**

Find this text near the end of `agentic/prompts/writer.txt`:
```
**IMPORTANT:**
- Write ALL sections in full - do not summarize or skip sections
```

Replace with:
```
**IMPORTANT:**
- Write ALL sections in full - do not summarize or skip sections
```

Then find the final line of the file:
```
Write the complete article now.
```

And add the anchoring rule immediately before it:
```
**FACTUAL GROUNDING (Critical):**
- Every specific claim — statistics, version numbers, percentages, benchmark results, named metrics — must trace back to one of the numbered VERIFIED FACTS above
- Do not assert specific technical details from your training knowledge; use ONLY what is in the VERIFIED FACTS list
- If a specific detail is NOT in the list, either omit it or hedge explicitly: "some sources suggest..." or "estimates vary..."

Write the complete article now.
```

- [ ] **Step 3: Run writer template tests to confirm they pass**

```bash
source .venv/bin/activate && pytest tests/test_writer_prompt.py::TestWriterTemplateFactInventory -v --no-header
```

Expected: All 6 writer tests pass.

- [ ] **Step 4: Commit**

```bash
git add agentic/prompts/writer.txt
git commit -m "feat: add verified facts inventory and anchoring rule to writer prompt"
```

---

### Task 3: Update revision.txt — same additions

**Files:**
- Modify: `agentic/prompts/revision.txt`

The `revision.txt` file has these sections:
1. System preamble
2. `**Original Topic:**`
3. `**Current Article:**` — `{{ article_content }}`
4. `**Editor Feedback (MUST ADDRESS ALL ISSUES):**` — `{{ editor_feedback }}`
5. `**Revision Requirements:**` block
6. `**IMPORTANT:**` block ending with `Now revise the article to address the editor feedback.`

- [ ] **Step 1: Add Block A — fact inventory — after the Editor Feedback section**

Find this text in `agentic/prompts/revision.txt`:
```
**Editor Feedback (MUST ADDRESS ALL ISSUES):**
{{ editor_feedback }}

**Revision Requirements:**
```

Replace with:
```
**Editor Feedback (MUST ADDRESS ALL ISSUES):**
{{ editor_feedback }}

{% if research_key_facts %}
**VERIFIED FACTS — Numbered Reference List:**
These facts were sourced and verified during research. Use them as your factual foundation when making specific claims.

{% for fact in research_key_facts %}
[FACT {{ loop.index }}] {{ fact.fact }}
  Source: {{ fact.source }}
  Confidence: {{ fact.get('confidence', 'medium') }}

{% endfor %}
{% endif %}

**Revision Requirements:**
```

- [ ] **Step 2: Add Block B — anchoring rule — before the final line**

Find the final line of `agentic/prompts/revision.txt`:
```
Now revise the article to address the editor feedback.
```

Replace with:
```
**FACTUAL GROUNDING (Critical):**
- Every specific claim — statistics, version numbers, percentages, benchmark results, named metrics — must trace back to one of the numbered VERIFIED FACTS above
- Do not assert specific technical details from your training knowledge; use ONLY what is in the VERIFIED FACTS list
- If a specific detail is NOT in the list, either omit it or hedge explicitly: "some sources suggest..." or "estimates vary..."

Now revise the article to address the editor feedback.
```

- [ ] **Step 3: Run revision template tests to confirm they pass**

```bash
source .venv/bin/activate && pytest tests/test_writer_prompt.py::TestRevisionTemplateFactInventory -v --no-header
```

Expected: All 4 revision tests pass.

- [ ] **Step 4: Run all new tests together**

```bash
source .venv/bin/activate && pytest tests/test_writer_prompt.py -v --no-header
```

Expected: All 10 tests pass.

- [ ] **Step 5: Confirm no regression in existing tests**

```bash
source .venv/bin/activate && pytest tests/test_tools.py tests/test_config.py -v --no-header 2>&1 | tail -10
```

Expected: Same results as before (3 pre-existing failures in `test_tools.py` — these are unrelated and were failing before this change).

- [ ] **Step 6: Commit**

```bash
git add agentic/prompts/revision.txt
git commit -m "feat: add verified facts inventory and anchoring rule to revision prompt"
```

---

### Task 4: Update writer.py — pass research_key_facts to both template renders

**Files:**
- Modify: `agentic/nodes/writer.py:83-91` (revision render)
- Modify: `agentic/nodes/writer.py:118-129` (initial write render)

- [ ] **Step 1: Update the REVISION MODE render call**

Find this block in `agentic/nodes/writer.py` (around line 80–91):
```python
        # Use revision prompt
        revision_template = PromptLoader.load("revision")
        current_date = datetime.now().strftime("%B %d, %Y")
        revision_prompt = revision_template.render(
            topic=topic,
            article_content=article_content_escaped,
            editor_feedback=feedback_escaped,
            word_count_target=word_count_target,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            current_date=current_date
        )
```

Replace with:
```python
        # Use revision prompt
        revision_template = PromptLoader.load("revision")
        current_date = datetime.now().strftime("%B %d, %Y")
        research_key_facts = state.get("research_key_facts", [])
        revision_prompt = revision_template.render(
            topic=topic,
            article_content=article_content_escaped,
            editor_feedback=feedback_escaped,
            word_count_target=word_count_target,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            current_date=current_date,
            research_key_facts=research_key_facts,
        )
```

- [ ] **Step 2: Update the INITIAL WRITE MODE render call**

Find this block in `agentic/nodes/writer.py` (around line 113–129):
```python
        # Use standard writer prompt
        writer_template = PromptLoader.load("writer")
        current_date = datetime.now().strftime("%B %d, %Y")
        headline_candidates = state.get("headline_candidates", [])
        audience_analysis = state.get("audience_analysis", "")
        writer_prompt = writer_template.render(
            topic=topic,
            tone=state.get("tone", Config.BLOG_TONE),
            instructions=instructions,
            research_summary=research_summary,
            audience_analysis=audience_analysis,
            headline_candidates=headline_candidates,
            word_count_target=word_count_target,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            current_date=current_date
        )
```

Replace with:
```python
        # Use standard writer prompt
        writer_template = PromptLoader.load("writer")
        current_date = datetime.now().strftime("%B %d, %Y")
        headline_candidates = state.get("headline_candidates", [])
        audience_analysis = state.get("audience_analysis", "")
        research_key_facts = state.get("research_key_facts", [])
        writer_prompt = writer_template.render(
            topic=topic,
            tone=state.get("tone", Config.BLOG_TONE),
            instructions=instructions,
            research_summary=research_summary,
            audience_analysis=audience_analysis,
            headline_candidates=headline_candidates,
            word_count_target=word_count_target,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            current_date=current_date,
            research_key_facts=research_key_facts,
        )
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

```bash
source .venv/bin/activate && pytest tests/test_writer_prompt.py tests/test_tools.py tests/test_config.py -v --no-header 2>&1 | tail -15
```

Expected: All 10 new tests pass. The 3 pre-existing `test_tools.py` failures remain (they were failing before, unrelated to this change).

- [ ] **Step 4: Commit**

```bash
git add agentic/nodes/writer.py
git commit -m "feat: pass research_key_facts to writer and revision prompt renders (issue #5)"
```

---

## Done

All three files updated, tests green. To validate end-to-end:

```bash
source .venv/bin/activate && python main.py "Your test topic" --debug
```

Check the console output for `INITIAL WRITE MODE` — the printed prompt length will be slightly larger (the fact inventory adds ~450 tokens). Then run a technical topic and check the LangSmith trace to verify `cache_read_input_tokens` and that the article's specific claims map to entries in the verified facts list.
