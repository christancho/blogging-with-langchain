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


@pytest.mark.parametrize(
    "name,args",
    [("writer", MINIMAL_WRITER_ARGS), ("revision", MINIMAL_REVISION_ARGS)],
)
class TestSessionNotesBlock:
    def test_block_rendered_with_notes(self, name, args):
        r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS, session_notes="I ran X")
        assert "AUTHOR'S SESSION NOTES" in r and "I ran X" in r
        assert "or to the AUTHOR'S SESSION NOTES" in r
        assert "the VERIFIED FACT wins" in r

    def test_no_block_without_notes(self, name, args):
        r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS, session_notes="")
        assert "AUTHOR'S SESSION NOTES" not in r
        assert "must trace back to one of the numbered VERIFIED FACTS above" in r

    def test_grounding_unchanged_without_notes(self, name, args):
        # Render WITHOUT passing session_notes at all (undefined variable path)
        r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS)
        assert "use ONLY what is in the VERIFIED FACTS list" in r
        assert "SESSION NOTES" not in r and "first person" not in r


VOICE_CONFLICT_PHRASES = {
    "writer": [
        'Begin with a relatable "you" scenario',
        'Use "you" and "your" frequently',
        '"I" or "we" sparingly',
    ],
    "revision": [
        'or a vivid "you" scenario',
        'Add more "you" and "your"',
    ],
}


@pytest.mark.parametrize(
    "name,args",
    [("writer", MINIMAL_WRITER_ARGS), ("revision", MINIMAL_REVISION_ARGS)],
)
class TestSessionNotesVoice:
    def test_conflicting_voice_lines_replaced_with_notes(self, name, args):
        r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS, session_notes="I ran X")
        for phrase in VOICE_CONFLICT_PHRASES[name]:
            assert phrase not in r
        assert "told in first person" in r

    def test_voice_lines_kept_without_notes(self, name, args):
        r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS)
        for phrase in VOICE_CONFLICT_PHRASES[name]:
            assert phrase in r
        assert "told in first person" not in r


CORRECTION_CLAUSE = "unless a VERIFIED FACT or a listed correction says otherwise"
CORRECTIONS_OVERRIDE = "The corrections above override the session notes"


class TestCorrectionsOverrideNotes:
    @pytest.mark.parametrize(
        "name,args",
        [("writer", MINIMAL_WRITER_ARGS), ("revision", MINIMAL_REVISION_ARGS)],
    )
    def test_reproduce_bullet_defers_to_facts(self, name, args):
        r = PromptLoader.load(name).render(**args, research_key_facts=SAMPLE_FACTS, session_notes="I ran X")
        assert CORRECTION_CLAUSE in r

    def test_fact_revision_with_notes_has_override(self):
        r = PromptLoader.load("revision").render(
            **MINIMAL_REVISION_ARGS, research_key_facts=SAMPLE_FACTS,
            session_notes="I ran X", is_fact_revision=True,
        )
        assert CORRECTIONS_OVERRIDE in r

    def test_fact_revision_without_notes_has_no_override(self):
        r = PromptLoader.load("revision").render(
            **MINIMAL_REVISION_ARGS, research_key_facts=SAMPLE_FACTS, is_fact_revision=True,
        )
        assert CORRECTIONS_OVERRIDE not in r
