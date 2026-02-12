"""
Unit tests for deep research tools
"""
import pytest
from tools import QueryGeneratorTool, ContentSynthesisTool


class TestQueryGeneratorTool:
    """Tests for QueryGeneratorTool"""

    def test_generates_queries(self):
        """Test that query generator produces queries"""
        tool = QueryGeneratorTool()
        queries = tool.generate_queries("Python async programming", num_queries=3)

        assert len(queries) == 3
        assert all(isinstance(q, str) for q in queries)
        assert all(len(q) > 10 for q in queries)  # Non-trivial queries

    def test_queries_include_year(self):
        """Test queries include current year for freshness"""
        tool = QueryGeneratorTool()
        queries = tool.generate_queries("React hooks", num_queries=2)

        # At least one query should mention a recent year
        from datetime import datetime
        current_year = str(datetime.now().year)
        has_year = any(current_year in q for q in queries)
        assert has_year, f"No query contains {current_year}"

    def test_respects_instructions(self):
        """Test that custom instructions are considered"""
        tool = QueryGeneratorTool()
        queries = tool.generate_queries(
            "Machine learning",
            instructions="Focus on beginner-friendly resources",
            num_queries=2
        )

        assert len(queries) == 2
        assert all(isinstance(q, str) for q in queries)


class TestContentSynthesisTool:
    """Tests for ContentSynthesisTool"""

    def test_synthesizes_content(self):
        """Test content synthesis produces structured output"""
        tool = ContentSynthesisTool()

        mock_contents = [
            {
                "url": "https://example.com/article1",
                "content": "Python async programming is essential for I/O-bound tasks. Expert John Doe says: 'Asyncio enables efficient concurrency.'"
            },
            {
                "url": "https://example.com/article2",
                "content": "Modern Python applications use async/await syntax. This improves performance significantly."
            }
        ]

        synthesis = tool.synthesize_content("Python async programming", mock_contents)

        # Check structure
        assert "summary" in synthesis
        assert "key_facts" in synthesis
        assert "quotes" in synthesis
        assert "themes" in synthesis
        assert isinstance(synthesis["key_facts"], list)
        assert isinstance(synthesis["quotes"], list)
        assert isinstance(synthesis["themes"], list)

    def test_handles_empty_content(self):
        """Test synthesis with no content"""
        tool = ContentSynthesisTool()

        synthesis = tool.synthesize_content("Test topic", [])

        # Should return minimal structure even with no content
        assert "summary" in synthesis
        assert isinstance(synthesis.get("key_facts", []), list)

    def test_handles_long_content(self):
        """Test synthesis with very long content (truncation)"""
        tool = ContentSynthesisTool()

        # Create a very long content string
        long_content = "A" * 50000  # 50k characters

        mock_contents = [
            {
                "url": "https://example.com/long-article",
                "content": long_content
            }
        ]

        # Should handle without error (content will be truncated)
        synthesis = tool.synthesize_content("Test topic", mock_contents)

        assert "summary" in synthesis
        assert isinstance(synthesis, dict)


@pytest.mark.integration
@pytest.mark.slow
class TestDeepResearchIntegration:
    """Integration tests for deep research workflow"""

    def test_query_generation_integration(self):
        """Test query generator with real LLM"""
        tool = QueryGeneratorTool()
        queries = tool.generate_queries(
            "LangGraph state management",
            instructions="Focus on practical examples",
            num_queries=3
        )

        assert len(queries) >= 2  # Should get at least 2 queries
        assert all("LangGraph" in q or "state" in q for q in queries)

    def test_content_synthesis_integration(self):
        """Test content synthesizer with realistic data"""
        tool = ContentSynthesisTool()

        mock_contents = [
            {
                "url": "https://example.com/article1",
                "content": """
                LangGraph is a powerful framework for building stateful workflows.
                According to the official documentation: "LangGraph enables developers
                to create complex multi-agent systems with ease." The key benefits include
                state management, conditional routing, and human-in-the-loop capabilities.
                """
            },
            {
                "url": "https://example.com/article2",
                "content": """
                State management in LangGraph follows a TypedDict pattern. This allows
                for type-safe state updates across nodes. Experts recommend using
                total=False for optional fields. The framework has been adopted by
                many production systems.
                """
            }
        ]

        synthesis = tool.synthesize_content("LangGraph state management", mock_contents)

        # Verify structured output
        assert synthesis["summary"]
        assert len(synthesis["summary"]) > 50  # Should have substantial summary
        assert len(synthesis["key_facts"]) > 0  # Should extract facts
        assert "sources_by_priority" in synthesis
