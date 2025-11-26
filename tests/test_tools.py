"""
Unit tests for tools
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock

from tools.seo_analyzer import SEOAnalysisTool, analyze_seo
from tools.html_formatter import HTMLFormatterTool, format_for_ghost, extract_metadata
from tools.tag_extractor import TagExtractionTool, extract_tags
from tools.content_analyzer import ContentAnalysisTool, analyze_content


class TestSEOAnalysisTool:
    """Tests for SEO Analysis Tool"""

    def test_word_count(self):
        """Test word counting"""
        tool = SEOAnalysisTool()
        content = "This is a test article with some words."
        result = tool._run(content)
        data = json.loads(result)

        assert data["word_count"] == 8

    def test_header_analysis(self):
        """Test header structure analysis"""
        tool = SEOAnalysisTool()
        content = """
# Main Title
## Section 1
## Section 2
### Subsection
"""
        result = tool._run(content)
        data = json.loads(result)

        assert data["headers"]["h1_count"] == 1
        assert data["headers"]["h2_count"] == 2
        assert data["headers"]["h3_count"] == 1

    def test_keyword_density(self):
        """Test keyword density analysis"""
        tool = SEOAnalysisTool()
        content = "Python programming is great. Python is powerful. Learn Python today."
        result = tool._run(content)
        data = json.loads(result)

        # Check that 'python' appears in top keywords
        keywords = [k["keyword"] for k in data["keyword_density"]["top_keywords"]]
        assert "python" in keywords


class TestHTMLFormatterTool:
    """Tests for HTML Formatter Tool"""

    def test_clean_markdown(self):
        """Test Markdown cleaning"""
        tool = HTMLFormatterTool()
        content = """
#NoSpace
##  ExtraSpace


Too many blank lines
"""
        result = tool._run(content)

        assert "# NoSpace" in result
        assert "## ExtraSpace" in result
        assert "\n\n\n" not in result  # No triple newlines

    def test_heading_hierarchy(self):
        """Test heading hierarchy fixing"""
        tool = HTMLFormatterTool()
        content = """
# First Title
# Second Title
## Section
"""
        result = tool._run(content)

        # Should convert second H1 to H2
        h1_count = result.count("\n# ")
        assert h1_count == 1

    def test_extract_title_and_description(self):
        """Test metadata extraction"""
        tool = HTMLFormatterTool()
        content = """
# My Great Article

This is the first paragraph that should become the description.

More content here.
"""
        metadata = tool.extract_title_and_description(content)

        assert metadata["title"] == "My Great Article"
        assert "first paragraph" in metadata["description"]

    def test_markdown_to_html(self):
        """Test Markdown to HTML conversion"""
        tool = HTMLFormatterTool()
        content = """
# Title
## Section
This is **bold** and *italic*.
[Link](https://example.com)
"""
        html = tool.markdown_to_html(content)

        assert "<h1>Title</h1>" in html
        assert "<h2>Section</h2>" in html
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html
        assert '<a href="https://example.com">Link</a>' in html


class TestTagExtractionTool:
    """Tests for Tag Extraction Tool"""

    def test_comma_separated_tags(self):
        """Test extracting comma-separated tags"""
        tool = TagExtractionTool()
        text = "python, machine-learning, AI, data science"
        result = tool._run(text)
        data = json.loads(result)

        assert len(data["tags"]) == 4
        assert "python" in data["tags"]
        assert "machine-learning" in data["tags"]

    def test_json_tags(self):
        """Test extracting tags from JSON"""
        tool = TagExtractionTool()
        text = '{"tags": ["python", "ai", "ml"]}'
        result = tool._run(text)
        data = json.loads(result)

        assert len(data["tags"]) == 3
        assert "python" in data["tags"]

    def test_labeled_tags(self):
        """Test extracting labeled tags"""
        tool = TagExtractionTool()
        text = "Tags: artificial-intelligence, machine-learning, deep-learning"
        result = tool._run(text)
        data = json.loads(result)

        assert "artificial-intelligence" in data["tags"]
        assert "machine-learning" in data["tags"]

    def test_tag_cleaning(self):
        """Test tag cleaning and normalization"""
        tool = TagExtractionTool()
        dirty_tag = '  "Machine Learning"  '
        clean_tag = tool._clean_tag(dirty_tag)

        assert clean_tag == "machine-learning"
        assert '"' not in clean_tag


class TestContentAnalysisTool:
    """Tests for Content Analysis Tool"""

    def test_word_count(self):
        """Test word counting"""
        tool = ContentAnalysisTool()
        content = "This is a test article with exactly eight words."
        result = tool._run(content)
        data = json.loads(result)

        assert data["word_count"] == 8

    def test_link_analysis(self):
        """Test link analysis"""
        tool = ContentAnalysisTool()
        content = """
This article has [one link](https://example.com) and
[another link](https://test.com) for testing.
"""
        result = tool._run(content)
        data = json.loads(result)

        assert data["links"]["total_links"] == 2
        assert data["links"]["markdown_links"] == 2

    def test_code_block_detection(self):
        """Test code block detection"""
        tool = ContentAnalysisTool()
        content = """
Here's some code:
```python
print("Hello World")
```
And inline `code` too.
"""
        result = tool._run(content)
        data = json.loads(result)

        assert data["code_blocks"]["code_block_count"] == 1
        assert data["code_blocks"]["inline_code_count"] >= 1
        assert data["code_blocks"]["has_code"] is True

    def test_structure_analysis(self):
        """Test document structure analysis"""
        tool = ContentAnalysisTool()
        content = """
# Main Title
## Section 1
## Section 2
## Section 3
## Section 4
"""
        result = tool._run(content)
        data = json.loads(result)

        assert data["structure"]["h1_count"] == 1
        assert data["structure"]["h2_count"] == 4
        assert data["structure"]["well_structured"] is True

    def test_quality_score_calculation(self):
        """Test quality score calculation"""
        tool = ContentAnalysisTool()

        # Create a high-quality article
        content = """
# Great Article

""" + " ".join(["word"] * 3500) + """

[Link1](http://example.com) [Link2](http://test.com)
[Link3](http://demo.com) [Link4](http://sample.com)
[Link5](http://foo.com) [Link6](http://bar.com)
[Link7](http://baz.com) [Link8](http://qux.com)
[Link9](http://abc.com) [Link10](http://def.com)
[Link11](http://ghi.com)

## Section 1
## Section 2
## Section 3
## Section 4
"""
        result = tool._run(content)
        data = json.loads(result)

        # Quality score should be relatively high
        assert data["quality_score"] > 0.5


# Integration tests
def test_analyze_seo_convenience_function():
    """Test convenience function for SEO analysis"""
    content = "# Test\n\nThis is a test article."
    result = analyze_seo(content)

    assert "word_count" in result
    assert "headers" in result


def test_format_for_ghost_convenience_function():
    """Test convenience function for Ghost formatting"""
    content = "#Test\n\nContent"
    result = format_for_ghost(content)

    assert "# Test" in result  # Should add space after #


def test_extract_metadata_convenience_function():
    """Test convenience function for metadata extraction"""
    content = "# Title\n\nDescription here."
    result = extract_metadata(content)

    assert result["title"] == "Title"
    assert "Description" in result["description"]


def test_extract_tags_convenience_function():
    """Test convenience function for tag extraction"""
    text = "python, ai, ml"
    result = extract_tags(text, max_tags=2)

    assert len(result) <= 2
    assert isinstance(result, list)


def test_analyze_content_convenience_function():
    """Test convenience function for content analysis"""
    content = "# Article\n\nThis is content."
    result = analyze_content(content)

    assert "word_count" in result
    assert "quality_score" in result
