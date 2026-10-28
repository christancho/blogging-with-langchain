"""
Tests that session notes drive research: priority URLs and query generation.
"""
from unittest.mock import MagicMock, patch

from agentic.nodes.research import research_node
from agentic.tools.query_generator import QueryGeneratorTool
from agentic.tools.url_fetcher import URLFetcherTool
from tests.test_prompt_escaping import CapturingLLM


def test_session_notes_in_query_prompt():
    """Session notes reach the query-generation prompt literally, with the notes section."""
    llm = CapturingLLM(reply="q1\nq2")
    notes = 'Ran `docker compose up` with {"x": 1}'
    with patch("agentic.tools.query_generator.Config.get_llm", llm):
        QueryGeneratorTool().generate_queries("Coolify", session_notes=notes, num_queries=2)
    assert "Author's Session Notes" in llm.calls[0]
    assert '{"x": 1}' in llm.calls[0]


def test_no_session_section_without_notes():
    """Without notes the prompt has no session notes section."""
    llm = CapturingLLM(reply="q1\nq2")
    with patch("agentic.tools.query_generator.Config.get_llm", llm):
        QueryGeneratorTool().generate_queries("Coolify", num_queries=2)
    assert "Author's Session Notes" not in llm.calls[0]


def _run_research(state):
    """Run research_node with mocked tools; return (url_fetcher, query_generator)."""
    url_fetcher = MagicMock()
    real = URLFetcherTool()
    url_fetcher.extract_urls_from_text.side_effect = real.extract_urls_from_text
    url_fetcher.fetch_url_content.side_effect = lambda u: {"url": u, "content": "c"}
    query_generator = MagicMock()
    query_generator.generate_queries.return_value = []
    search = MagicMock()
    search._run.return_value = '{"results": []}'
    synth = MagicMock()
    synth.synthesize_content.return_value = {"summary": "", "key_facts": []}
    validator = MagicMock()
    validator.validate_urls.side_effect = lambda urls, **kw: (urls, [])
    with patch("agentic.tools.BraveSearchTool", return_value=search), \
         patch("agentic.tools.URLFetcherTool", return_value=url_fetcher), \
         patch("agentic.tools.QueryGeneratorTool", return_value=query_generator), \
         patch("agentic.tools.ContentSynthesisTool", return_value=synth), \
         patch("agentic.tools.LinkValidatorTool", return_value=validator):
        research_node(state)
    return url_fetcher, query_generator


def test_research_fetches_session_note_urls():
    """URLs from instructions and session notes are fetched once each."""
    state = {
        "topic": "T",
        "instructions": "see https://a.example/doc",
        "session_notes": "used https://b.example/x and https://a.example/doc",
    }
    url_fetcher, _ = _run_research(state)
    fetched = [c.args[0] for c in url_fetcher.fetch_url_content.call_args_list]
    assert sorted(fetched) == ["https://a.example/doc", "https://b.example/x"]


def test_research_passes_session_notes_to_query_generator():
    """Session notes are forwarded to generate_queries as a keyword."""
    state = {"topic": "T", "instructions": "", "session_notes": "notes here"}
    _, query_generator = _run_research(state)
    assert query_generator.generate_queries.call_args.kwargs["session_notes"] == "notes here"
