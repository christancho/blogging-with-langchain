"""
Tests that user-supplied text containing braces reaches the LLM prompt literally
instead of crashing ChatPromptTemplate with a missing-variables KeyError.
"""
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agentic.nodes.audience_analysis import audience_analysis_node
from agentic.nodes.editor import editor_node
from agentic.nodes.seo import seo_node

BRACES = 'Use ${POSTGRES_PASSWORD} and {"a": 1} and f() { echo hi; }'


class CapturingLLM:
    """Stand-in for Config.get_llm(): records prompt messages, returns a canned reply."""

    def __init__(self, reply="ok"):
        """Store the canned reply and initialise the list of captured prompts."""
        self.calls = []
        self.reply = reply

    def __call__(self, *args, **kwargs):
        """Return a runnable that records the rendered prompt and replies with the canned text."""
        def _run(prompt_value):
            self.calls.append("\n".join(m.content for m in prompt_value.to_messages()))
            return AIMessage(content=self.reply)
        return RunnableLambda(_run)


def _assert_literal(llm):
    """Assert the LLM was invoked and received BRACES verbatim."""
    assert llm.calls, "LLM never invoked — prompt construction failed"
    assert BRACES in llm.calls[0]


def test_audience_analysis_escapes_instructions():
    """Audience analysis passes brace-laden instructions to the LLM literally."""
    llm = CapturingLLM()
    state = {"topic": "Databases", "instructions": BRACES, "research_summary": "summary"}
    with patch("agentic.nodes.audience_analysis.Config.get_llm", llm):
        audience_analysis_node(state)
    _assert_literal(llm)


def test_seo_escapes_instructions():
    """SEO node passes brace-laden instructions to the LLM literally."""
    llm = CapturingLLM()
    state = {
        "article_title": "Title",
        "formatted_content": "# Title\n\nShort article.",
        "instructions": BRACES,
    }
    with patch("agentic.nodes.seo.Config.get_llm", llm):
        seo_node(state)
    _assert_literal(llm)


def test_editor_escapes_instructions():
    """Editor node passes brace-laden instructions to the LLM literally."""
    llm = CapturingLLM()
    state = {
        "formatted_content": "# Title\n\n## Section\n\nShort article body.",
        "instructions": BRACES,
    }
    with patch("agentic.nodes.editor.Config.get_llm", llm):
        editor_node(state)
    _assert_literal(llm)
