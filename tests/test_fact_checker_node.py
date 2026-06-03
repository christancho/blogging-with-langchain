"""
Unit tests for fact_checker_node state updates
"""
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage
from agentic.nodes.fact_checker import _build_feedback


class TestBuildFeedback:
    def test_single_false_verdict(self):
        verdicts = [{
            "claim": "X has 100 stars",
            "verdict": "false",
            "correct_information": "X has 200 stars",
            "source_url": "https://example.com",
            "confidence": "high"
        }]
        result = _build_feedback(verdicts)
        assert "INCORRECT CLAIM: X has 100 stars" in result
        assert "CORRECT INFORMATION: X has 200 stars" in result
        assert "SOURCE: https://example.com" in result

    def test_multiple_false_verdicts_numbered(self):
        verdicts = [
            {"claim": "A", "verdict": "false", "correct_information": "B", "source_url": "https://a.com", "confidence": "high"},
            {"claim": "C", "verdict": "false", "correct_information": "D", "source_url": "https://c.com", "confidence": "high"},
        ]
        result = _build_feedback(verdicts)
        assert "1. INCORRECT CLAIM: A" in result
        assert "2. INCORRECT CLAIM: C" in result


class TestFactCheckerStateUpdates:
    """Test that fact_checker_node updates research_key_facts and accumulates feedback."""

    def _make_state(self, article="Test article.", fact_revision_count=0,
                    existing_facts=None, existing_feedback=""):
        return {
            "article_content": article,
            "fact_revision_count": fact_revision_count,
            "fact_max_revisions": 3,
            "research_key_facts": existing_facts or [],
            "fact_check_feedback": existing_feedback,
        }

    def _make_llm_mock(self, mock_get_llm, *responses):
        """Configure mock_get_llm so the returned LLM cycles through AIMessage responses.

        LangChain's `prompt | llm | StrOutputParser()` chain calls the LLM as a
        plain callable: `llm(prompt_value)`. Setting `side_effect` on the LLM
        object (i.e. `mock_get_llm.return_value`) makes it return successive
        AIMessage objects, which StrOutputParser then unwraps to strings.
        """
        mock_get_llm.return_value.side_effect = [AIMessage(content=r) for r in responses]

    @patch("agentic.nodes.fact_checker.Config.get_llm")
    @patch("agentic.nodes.fact_checker.BraveSearchTool")
    @patch("agentic.nodes.fact_checker.URLFetcherTool")
    def test_corrections_appended_to_research_key_facts(self, mock_url, mock_search, mock_llm):
        from agentic.nodes.fact_checker import fact_checker_node

        existing_facts = [{"fact": "A is true", "source": "https://a.com", "confidence": "high"}]
        state = self._make_state(existing_facts=existing_facts)

        # LLM returns: phase-1 claim list, then phase-2 verdict
        claims_json = '[{"claim": "Y is false", "context": "ctx", "suggested_query": "Y query"}]'
        verdict_json = ('{"claim": "Y is false", "verdict": "false",'
                        ' "correct_information": "Y is actually Z",'
                        ' "source_url": "https://y.com", "confidence": "high"}')

        with patch("agentic.nodes.fact_checker.PromptLoader") as mock_loader, \
             patch("agentic.nodes.fact_checker._gather_search_content", return_value="some content"):

            mock_loader.load.return_value.render.return_value = "prompt text"
            self._make_llm_mock(mock_llm, claims_json, verdict_json)

            result = fact_checker_node(state)

        assert result["fact_check_status"] == "failed"
        updated_facts = result["research_key_facts"]
        assert len(updated_facts) == 2
        assert updated_facts[1]["fact"] == "Y is actually Z"
        assert updated_facts[1]["source"] == "https://y.com"
        assert updated_facts[1]["confidence"] == "high"

    @patch("agentic.nodes.fact_checker.Config.get_llm")
    @patch("agentic.nodes.fact_checker.BraveSearchTool")
    @patch("agentic.nodes.fact_checker.URLFetcherTool")
    def test_feedback_accumulated_across_passes(self, mock_url, mock_search, mock_llm):
        from agentic.nodes.fact_checker import fact_checker_node

        existing_feedback = "1. INCORRECT CLAIM: Old claim\n   CORRECT INFORMATION: Old fix\n"
        state = self._make_state(
            fact_revision_count=1,
            existing_feedback=existing_feedback
        )

        claims_json = '[{"claim": "New claim", "context": "ctx", "suggested_query": "q"}]'
        verdict_json = ('{"claim": "New claim", "verdict": "false",'
                        ' "correct_information": "New fix",'
                        ' "source_url": "https://new.com", "confidence": "high"}')

        with patch("agentic.nodes.fact_checker.PromptLoader") as mock_loader, \
             patch("agentic.nodes.fact_checker._gather_search_content", return_value="some content"):

            mock_loader.load.return_value.render.return_value = "prompt text"
            self._make_llm_mock(mock_llm, claims_json, verdict_json)

            result = fact_checker_node(state)

        feedback = result["fact_check_feedback"]
        assert "Old claim" in feedback
        assert "New claim" in feedback

    @patch("agentic.nodes.fact_checker.Config.get_llm")
    @patch("agentic.nodes.fact_checker.BraveSearchTool")
    @patch("agentic.nodes.fact_checker.URLFetcherTool")
    def test_verdicts_without_correct_info_not_added_to_facts(self, mock_url, mock_search, mock_llm):
        from agentic.nodes.fact_checker import fact_checker_node

        state = self._make_state()

        claims_json = '[{"claim": "Z is false", "context": "ctx", "suggested_query": "q"}]'
        verdict_json = ('{"claim": "Z is false", "verdict": "false",'
                        ' "correct_information": null, "source_url": null, "confidence": "low"}')

        with patch("agentic.nodes.fact_checker.PromptLoader") as mock_loader, \
             patch("agentic.nodes.fact_checker._gather_search_content", return_value="some content"):

            mock_loader.load.return_value.render.return_value = "prompt text"
            self._make_llm_mock(mock_llm, claims_json, verdict_json)

            result = fact_checker_node(state)

        # Both correct_information and source_url must be present; either missing means excluded
        assert result.get("research_key_facts", []) == []

    @patch("agentic.nodes.fact_checker.Config.get_llm")
    @patch("agentic.nodes.fact_checker.BraveSearchTool")
    @patch("agentic.nodes.fact_checker.URLFetcherTool")
    def test_duplicate_corrections_not_added_twice(self, mock_url, mock_search, mock_llm):
        from agentic.nodes.fact_checker import fact_checker_node

        # Simulate a fact that was already added in a prior pass
        existing_facts = [{"fact": "Y is actually Z", "source": "https://y.com", "confidence": "high"}]
        state = self._make_state(existing_facts=existing_facts)

        claims_json = '[{"claim": "Y is false", "context": "ctx", "suggested_query": "Y query"}]'
        verdict_json = ('{"claim": "Y is false", "verdict": "false",'
                        ' "correct_information": "Y is actually Z",'
                        ' "source_url": "https://y.com", "confidence": "high"}')

        with patch("agentic.nodes.fact_checker.PromptLoader") as mock_loader, \
             patch("agentic.nodes.fact_checker._gather_search_content", return_value="some content"):

            mock_loader.load.return_value.render.return_value = "prompt text"
            self._make_llm_mock(mock_llm, claims_json, verdict_json)

            result = fact_checker_node(state)

        # Should still be 1 fact — deduplication prevented the append
        assert len(result["research_key_facts"]) == 1
