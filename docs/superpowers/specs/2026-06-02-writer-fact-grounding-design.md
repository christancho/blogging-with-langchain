# Writer Fact Grounding Design

**Issue:** #5 — Investigate writer/fact-checker friction: false statements despite deep research

## Problem

The writer node occasionally produces false or unverifiable specific claims — statistics, version numbers, percentages, benchmark results — even when the research node has gathered solid sources. Root cause (confirmed via LangSmith traces): the writer is not ignoring the research; it is *extending beyond it*, fabricating specific technical details from training knowledge to fulfil the prompt's instruction to be "specific and concrete." The fact checker catches these downstream but cannot always correct them within the 3-revision budget, resulting in force-passed articles with known false claims.

## Approach

Structured key fact injection with an anchoring rule. The research node already extracts `research_key_facts` as a structured list of `{fact, source, confidence}` and stores it in state. The writer never sees this as a structured, scannable inventory — only as prose buried in `research_summary`. By surfacing it as a numbered reference list and adding an explicit anchoring rule, the writer has a clear bounded set of facts it can assert confidently, and a clear signal to hedge or omit anything outside it.

This is a prevention fix (issue #5 approach A). If it proves insufficient, the next step is improving the fact-checker correction loop (approach B).

## Changes

Three files change; no new nodes, no new LLM calls, no schema changes.

### 1. `agentic/nodes/writer.py`

Pass `research_key_facts` from state into both the initial write and revision template renders.

**Initial write (INITIAL WRITE MODE block):**
```python
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
    research_key_facts=research_key_facts,   # NEW
)
```

**Revision (REVISION MODE block):**
```python
research_key_facts = state.get("research_key_facts", [])
revision_prompt = revision_template.render(
    topic=topic,
    article_content=article_content_escaped,
    editor_feedback=feedback_escaped,
    word_count_target=word_count_target,
    min_word_count=min_word_count,
    max_word_count=max_word_count,
    current_date=current_date,
    research_key_facts=research_key_facts,   # NEW
)
```

### 2. `agentic/prompts/writer.txt`

Add two blocks.

**Block A — Numbered fact inventory** (inserted after the existing `**Research Context:**` section):

```jinja2
{% if research_key_facts %}
**VERIFIED FACTS — Numbered Reference List:**
These facts are sourced and verified from the research phase. Use them as your factual foundation.

{% for fact in research_key_facts %}
[FACT {{ loop.index }}] {{ fact.fact }}
  Source: {{ fact.source }}
  Confidence: {{ fact.get('confidence', 'medium') }}

{% endfor %}
{% endif %}
```

**Block B — Anchoring rule** (inserted in the existing `**IMPORTANT:**` section, before the final "Write the complete article now." line):

```
**FACTUAL GROUNDING (Critical):**
- Every specific claim — statistics, version numbers, percentages, benchmark results, named metrics — must trace back to one of the numbered VERIFIED FACTS above
- Do not assert specific technical details from your training knowledge; use ONLY what is in the VERIFIED FACTS list
- If a specific detail is NOT in the list, either omit it or hedge explicitly: "some sources suggest..." or "estimates vary..."
```

### 3. `agentic/prompts/revision.txt`

Same two blocks added in the same positions, so that revision passes do not re-introduce hallucinations while fixing editor feedback.

## Data Flow

```
research_node
  → research_key_facts: [{fact, source, confidence}, ...]  (already in state)

writer_node (initial write)
  → template.render(..., research_key_facts=research_key_facts)
  → writer.txt renders numbered list + anchoring rule
  → LLM writes article constrained to the list

writer_node (revision)
  → template.render(..., research_key_facts=research_key_facts)
  → revision.txt renders numbered list + anchoring rule
  → LLM revises article still constrained to the list
```

## Edge Cases

- **Empty `research_key_facts`:** The `{% if research_key_facts %}` guard ensures the block is omitted gracefully. The writer falls back to the existing `research_summary` only.
- **Jinja2 `fact.get()`:** `research_key_facts` items are dicts; `.get('confidence', 'medium')` is valid.
- **Token cost:** ~15 key facts × ~30 tokens each ≈ 450 additional tokens per request. Acceptable overhead.
- **Revision prompt already has `research_summary`:** The key facts list is additive; both remain present.

## Success Criteria

- Fact checker `false` verdict count drops significantly on technical articles (target: 0–1 per run vs. the 6 seen in the prompt-caching article).
- No regression in article quality scores (editorial approval rate stays ≥ current baseline).
- `force_passed` fact check status should become rare or eliminated.

## Out of Scope

- Changing the fact checker correction loop (approach B — held in reserve).
- Lowering temperature (approach C — not needed if prompt changes are sufficient).
- Adding a new pre-write node.
