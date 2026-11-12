"""
Tests that every pipeline node/tool passes its routing_context to Config.get_llm,
so the JEV router can judge how hard each invocation is.
"""
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agentic.nodes.audience_analysis import audience_analysis_node
from agentic.nodes.editor import editor_node
from agentic.nodes.fact_checker import fact_checker_node
from agentic.nodes.formatter import formatter_node
from agentic.nodes.seo import seo_node
from agentic.nodes.writer import writer_node
from agentic.tools.content_synthesizer import ContentSynthesisTool
from agentic.tools.query_generator import QueryGeneratorTool

TOPIC = "Vector databases"


class RoutingRecorder:
    """Stand-in for Config.get_llm(): records node name and routing_context, returns a canned reply."""

    def __init__(self, reply="[]"):
        """Store the canned reply and initialise the recorded calls."""
        self.reply = reply
        self.nodes = []
        self.contexts = []

    def __call__(self, node, *args, **kwargs):
        """Record the call and return a runnable replying with the canned text."""
        self.nodes.append(node)
        self.contexts.append(kwargs.get("routing_context"))
        return RunnableLambda(lambda _prompt: AIMessage(content=self.reply))

    @property
    def context(self):
        """Return the first recorded routing_context, failing if get_llm was never called with one."""
        assert self.contexts, "Config.get_llm was never called"
        assert self.contexts[0] is not None, "routing_context was not passed"
        return self.contexts[0]


def test_query_generator_context():
    """Query generator passes topic and instructions."""
    rec = RoutingRecorder()
    with patch("agentic.tools.query_generator.Config.get_llm", rec):
        QueryGeneratorTool().generate_queries(TOPIC, "be brief")
    assert rec.nodes[0] == "query_generator"
    assert rec.context == {"topic": TOPIC, "instructions": "be brief"}


def test_content_synthesizer_context():
    """Content synthesizer passes topic, source count and total source chars."""
    rec = RoutingRecorder(reply="{}")
    fetched = [{"url": "https://a.com", "content": "abcd", "type": "web"},
               {"url": "https://b.com", "content": "ef", "type": "web"}]
    with patch("agentic.tools.content_synthesizer.Config.get_llm", rec):
        ContentSynthesisTool().synthesize_content(TOPIC, fetched)
    assert rec.nodes[0] == "content_synthesizer"
    assert rec.context == {"topic": TOPIC, "source count": 2, "total source chars": 6}


def test_audience_analysis_context():
    """Audience analysis passes topic and instructions."""
    rec = RoutingRecorder(reply="insights")
    state = {"topic": TOPIC, "instructions": "for CTOs", "research_summary": "s"}
    with patch("agentic.nodes.audience_analysis.Config.get_llm", rec):
        audience_analysis_node(state)
    assert rec.nodes[0] == "audience_analysis"
    assert rec.context == {"topic": TOPIC, "instructions": "for CTOs"}


def test_writer_context():
    """Writer passes topic, instructions, research length, revision count and both feedbacks."""
    rec = RoutingRecorder(reply="# T\n\nbody")
    state = {
        "topic": TOPIC, "instructions": "be brief", "research_summary": "12345",
        "revision_count": 2, "approval_feedback": "tighten", "fact_check_feedback": "",
    }
    with patch("agentic.nodes.writer.Config.get_llm", rec):
        writer_node(state)
    assert rec.nodes[0] == "writer"
    assert rec.context == {
        "topic": TOPIC, "instructions": "be brief", "research length": 5,
        "revision count": 2, "latest editor feedback": "tighten",
        "latest fact-check feedback": None,
    }


def test_fact_checker_context():
    """Fact checker passes topic and draft word count."""
    rec = RoutingRecorder(reply="[]")
    state = {"topic": TOPIC, "article_content": "one two three four"}
    with patch("agentic.nodes.fact_checker.Config.get_llm", rec):
        fact_checker_node(state, {})
    assert rec.nodes[0] == "fact_checker"
    assert rec.context == {"topic": TOPIC, "draft word count": 4}


def test_editor_context():
    """Editor passes topic, analyzed draft word count and revision count."""
    rec = RoutingRecorder(reply="{}")
    state = {"topic": TOPIC, "formatted_content": "# T\n\n## S\n\nShort body text.", "revision_count": 1}
    with patch("agentic.nodes.editor.Config.get_llm", rec):
        editor_node(state)
    assert rec.nodes[0] == "editor"
    assert set(rec.context) == {"topic", "draft word count", "revision count"}
    assert rec.context["topic"] == TOPIC
    assert rec.context["revision count"] == 1
    assert isinstance(rec.context["draft word count"], int)


def test_seo_context():
    """SEO passes topic and article word count."""
    rec = RoutingRecorder(reply="{}")
    state = {"topic": TOPIC, "article_title": "T", "formatted_content": "one two three"}
    with patch("agentic.nodes.seo.Config.get_llm", rec):
        seo_node(state)
    assert rec.nodes[0] == "seo"
    assert rec.context == {"topic": TOPIC, "article word count": 3}


def test_formatter_context():
    """Formatter passes topic and article word count."""
    rec = RoutingRecorder(reply="# T\n\nbody")
    state = {"topic": TOPIC, "article_content": "one two three four five"}
    with patch("agentic.nodes.formatter.Config.get_llm", rec):
        formatter_node(state)
    assert rec.nodes[0] == "formatter"
    assert rec.context == {"topic": TOPIC, "article word count": 5}
