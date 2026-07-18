import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from agentic.tools.content_synthesizer import ContentSynthesisTool


class TestContentSynthesisTool:
    """Tests for ContentSynthesisTool's JSON parsing of LLM output."""

    @patch("agentic.tools.content_synthesizer.Config.get_llm")
    def test_parses_json_with_literal_newline_in_string(self, mock_get_llm):
        """LLMs sometimes emit a raw (unescaped) newline inside a JSON string
        value instead of an escaped \\n -- json.loads() in its default strict
        mode rejects this with 'Invalid control character'. The tool should
        still parse the response instead of silently falling back to an
        empty synthesis structure.
        """
        raw_response = (
            '{"summary": "First paragraph.\n'
            'Second paragraph.", "key_facts": [], "quotes": [], '
            '"themes": [], "sources_by_priority": []}'
        )
        mock_get_llm.return_value.side_effect = [AIMessage(content=raw_response)]

        tool = ContentSynthesisTool()
        result = tool.synthesize_content(
            "test topic",
            [{"url": "https://example.com", "content": "x", "type": "web"}],
        )

        assert result["summary"] == "First paragraph.\nSecond paragraph."
        assert result["summary"] != "Synthesis failed - see raw research"
