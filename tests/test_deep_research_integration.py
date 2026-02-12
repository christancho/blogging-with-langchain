"""
Integration tests for deep research mode
"""
import pytest
from graph import generate_blog_post


@pytest.mark.integration
@pytest.mark.slow
class TestDeepResearchEndToEnd:
    """End-to-end tests for deep research workflow"""

    def test_deep_research_workflow(self):
        """Test complete deep research workflow"""
        result = generate_blog_post(
            topic="Python decorators tutorial",
            deep_research=True
        )

        # Verify deep research was executed
        assert result.get("deep_research_enabled") is True
        assert len(result.get("research_queries", [])) > 0
        assert len(result.get("research_fetched_urls", [])) > 0
        assert len(result.get("research_key_facts", [])) > 0

        # Verify structured data exists
        structured = result.get("research_structured_data", {})
        assert "summary" in structured
        assert "key_facts" in structured
        assert "quotes" in structured
        assert "themes" in structured

        # Verify writer received enhanced research
        assert result.get("final_content") is not None
        assert len(result.get("final_content", "").split()) >= 100  # Substantial content

    def test_standard_mode_unchanged(self):
        """Test that standard mode still works as before"""
        result = generate_blog_post(
            topic="Python list comprehensions",
            deep_research=False
        )

        # Verify standard mode was executed
        assert result.get("deep_research_enabled") is False
        assert "research_queries" not in result or not result.get("research_queries")

        # Verify standard research still produces output
        assert result.get("research_summary") is not None
        assert result.get("final_content") is not None

    def test_deep_research_with_instructions(self):
        """Test deep research with custom instructions"""
        result = generate_blog_post(
            topic="FastAPI best practices",
            instructions="Focus on production deployment and security",
            deep_research=True
        )

        # Verify deep research considered instructions
        assert result.get("deep_research_enabled") is True
        queries = result.get("research_queries", [])
        assert len(queries) > 0

        # At least one query should relate to instructions
        has_relevant_query = any(
            "production" in q.lower() or
            "deployment" in q.lower() or
            "security" in q.lower()
            for q in queries
        )
        assert has_relevant_query, "No queries related to custom instructions"

    def test_deep_research_error_handling(self):
        """Test deep research handles errors gracefully"""
        # Use a very obscure topic that might fail some steps
        result = generate_blog_post(
            topic="xyzabc123 nonexistent topic",
            deep_research=True
        )

        # Should still complete without crashing
        assert result.get("deep_research_enabled") is True

        # Should have attempted research even if some steps failed
        research_results = result.get("research_results", {})
        assert research_results.get("mode") == "deep"

        # Check for errors but don't require success
        # (research might legitimately fail for nonsense topics)
        assert "errors" in result


@pytest.mark.integration
class TestDeepResearchComponents:
    """Component-level integration tests"""

    def test_query_generation_component(self):
        """Test query generation in isolation"""
        from tools import QueryGeneratorTool

        tool = QueryGeneratorTool()
        queries = tool.generate_queries(
            "Docker containerization",
            num_queries=4
        )

        assert len(queries) == 4
        assert all("docker" in q.lower() or "container" in q.lower() for q in queries)

    def test_synthesis_component(self):
        """Test content synthesis in isolation"""
        from tools import ContentSynthesisTool

        tool = ContentSynthesisTool()

        mock_contents = [
            {
                "url": "https://docs.docker.com",
                "content": "Docker is a platform for developing, shipping, and running applications in containers. Containers provide isolation and consistency across environments."
            },
            {
                "url": "https://kubernetes.io/docs",
                "content": "Kubernetes orchestrates containerized applications. It manages scaling, deployment, and networking for container workloads."
            }
        ]

        synthesis = tool.synthesize_content("Docker containerization", mock_contents)

        assert synthesis["summary"]
        assert len(synthesis["key_facts"]) > 0
        assert len(synthesis["themes"]) > 0

    def test_url_fetching_component(self):
        """Test URL fetching works correctly"""
        from tools import URLFetcherTool

        tool = URLFetcherTool()

        # Test with a reliable URL
        result = tool.fetch_url_content("https://example.com")

        # Should fetch successfully or handle error gracefully
        assert "url" in result
        assert "type" in result
        # content may or may not exist depending on fetch success


@pytest.mark.benchmark
class TestDeepResearchPerformance:
    """Performance and cost tracking tests"""

    def test_deep_research_cost_estimation(self):
        """Verify deep research cost is within expected range"""
        # This is a benchmark test - only run when explicitly requested
        pytest.skip("Benchmark test - run with pytest -m benchmark")

        result = generate_blog_post(
            topic="GraphQL API design",
            deep_research=True
        )

        # Check cost tracking (if LangSmith is enabled)
        cost_breakdown = result.get("cost_breakdown", {})

        # Deep research should be more expensive than standard
        # but still within reasonable bounds ($0.50 max)
        if cost_breakdown:
            total_cost = result.get("total_cost_usd", 0)
            assert total_cost < 0.50, f"Deep research cost ${total_cost} exceeds $0.50"

    def test_deep_research_time_estimation(self):
        """Verify deep research completes within expected timeframe"""
        # This is a benchmark test - only run when explicitly requested
        pytest.skip("Benchmark test - run with pytest -m benchmark")

        import time

        start = time.time()
        result = generate_blog_post(
            topic="Redis caching patterns",
            deep_research=True
        )
        duration = time.time() - start

        # Should complete in under 5 minutes
        assert duration < 300, f"Deep research took {duration}s (>5 min)"

        # Verify it actually did deep research
        assert result.get("deep_research_enabled") is True
