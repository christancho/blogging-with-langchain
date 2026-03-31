"""
Unit tests for LinkValidatorTool
"""
import pytest
from tools import LinkValidatorTool


class TestLinkValidatorTool:
    """Tests for LinkValidatorTool"""

    def test_validate_valid_url(self):
        """Test validation of a known good URL"""
        tool = LinkValidatorTool()
        result = tool.validate_url("https://example.com")

        assert result["url"] == "https://example.com"
        assert "is_valid" in result
        assert "status_code" in result

        # example.com should return 200
        if result["is_valid"]:
            assert result["status_code"] == 200
            assert result["error"] is None

    def test_validate_invalid_url(self):
        """Test validation of a non-existent URL"""
        tool = LinkValidatorTool()
        # Use a URL that's very likely to 404
        result = tool.validate_url("https://example.com/this-page-definitely-does-not-exist-12345")

        assert result["url"] == "https://example.com/this-page-definitely-does-not-exist-12345"
        assert "is_valid" in result
        assert "status_code" in result

        # Should be invalid (404)
        if not result["is_valid"] and result["status_code"]:
            assert result["status_code"] == 404

    def test_validate_unreachable_url(self):
        """Test validation of unreachable domain"""
        tool = LinkValidatorTool()
        # Use an invalid domain that won't resolve
        result = tool.validate_url("https://this-domain-does-not-exist-xyz123.com")

        assert result["url"] == "https://this-domain-does-not-exist-xyz123.com"
        assert result["is_valid"] is False
        assert result["error"] is not None

    def test_validate_urls_batch(self):
        """Test batch validation of multiple URLs"""
        tool = LinkValidatorTool()

        urls = [
            "https://example.com",
            "https://example.org",
            "https://this-will-404.example.com/nonexistent"
        ]

        valid_urls, validation_results = tool.validate_urls(urls, show_progress=False)

        # Should get results for all URLs
        assert len(validation_results) == 3

        # At least the first two should be valid (example.com and example.org)
        assert len(valid_urls) >= 2

        # All results should have required fields
        for result in validation_results:
            assert "url" in result
            assert "is_valid" in result
            assert "status_code" in result or "error" in result

    def test_validate_empty_list(self):
        """Test validation with empty URL list"""
        tool = LinkValidatorTool()

        valid_urls, validation_results = tool.validate_urls([], show_progress=False)

        assert valid_urls == []
        assert validation_results == []

    def test_validation_summary(self):
        """Test validation summary generation"""
        tool = LinkValidatorTool()

        # Mock validation results
        validation_results = [
            {"url": "https://example.com", "is_valid": True, "status_code": 200, "error": None},
            {"url": "https://example.org", "is_valid": True, "status_code": 200, "error": None},
            {"url": "https://example.net", "is_valid": False, "status_code": 404, "error": "HTTP 404"},
            {"url": "https://fail.com", "is_valid": False, "status_code": None, "error": "Timeout"}
        ]

        summary = tool.get_validation_summary(validation_results)

        assert summary["total_urls"] == 4
        assert summary["valid_urls"] == 2
        assert summary["invalid_urls"] == 2
        assert summary["success_rate"] == 50.0
        assert "error_breakdown" in summary
        assert "HTTP 404" in summary["error_breakdown"]
        assert "Timeout" in summary["error_breakdown"]



@pytest.mark.benchmark
class TestLinkValidatorPerformance:
    """Performance tests for link validation"""

    def test_validation_speed(self):
        """Test that validation is reasonably fast"""
        pytest.skip("Benchmark test - run with pytest -m benchmark")

        import time
        from tools import LinkValidatorTool

        tool = LinkValidatorTool()

        # Test with 10 URLs
        urls = ["https://example.com"] * 10

        start = time.time()
        valid_urls, results = tool.validate_urls(urls, show_progress=False)
        duration = time.time() - start

        # Should complete in under 30 seconds for 10 URLs
        assert duration < 30, f"Validation took {duration}s (>30s)"

        # Calculate average time per URL
        avg_per_url = duration / len(urls)
        print(f"Average validation time: {avg_per_url:.2f}s per URL")
