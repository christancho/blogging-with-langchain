"""
Tag Extraction Tool for SEO tags
"""
import re
import json
from typing import List, Set
from langchain.tools import BaseTool

from config import Config


class TagExtractionTool(BaseTool):
    """Tool for extracting and cleaning SEO tags"""

    name: str = "tag_extractor"
    description: str = """
    Extracts and cleans SEO tags from content or SEO analysis output.
    Removes duplicates and limits to maximum number of tags.
    Input should be text containing tags (comma-separated or in a list).
    Returns a cleaned list of tags.
    """

    def _run(self, input_text: str) -> str:
        """
        Extract and clean tags from input

        Args:
            input_text: Text containing tags

        Returns:
            JSON string with cleaned tags list
        """
        tags = self._extract_tags(input_text)

        # Limit to max tags
        tags = tags[:Config.MAX_TAGS]

        return json.dumps({"tags": tags}, indent=2)

    async def _arun(self, input_text: str) -> str:
        """Async version - falls back to sync"""
        return self._run(input_text)

    def _extract_tags(self, text: str) -> List[str]:
        """
        Extract tags from various text formats

        Handles:
        - Comma-separated: "tag1, tag2, tag3"
        - List format: "['tag1', 'tag2', 'tag3']"
        - Labeled format: "Tags: tag1, tag2, tag3"
        - JSON format: {"tags": ["tag1", "tag2"]}
        """
        tags: Set[str] = set()

        # Try JSON first
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tags" in data:
                tags.update(self._clean_tag(tag) for tag in data["tags"])
                return list(tags)
            elif isinstance(data, list):
                tags.update(self._clean_tag(tag) for tag in data)
                return list(tags)
        except json.JSONDecodeError:
            pass

        # Try multiple regex patterns
        patterns = [
            r'Tags?:\s*\[([^\]]+)\]',  # Tags: [tag1, tag2]
            r'Tags?:\s*([^\n]+)',  # Tags: tag1, tag2, tag3
            r'\[([^\]]+)\]',  # [tag1, tag2]
            r'tags?:\s*([^\n]+)',  # tags: tag1, tag2 (lowercase)
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Split by comma and clean
                tag_parts = re.split(r'[,;]', match)
                for tag in tag_parts:
                    cleaned = self._clean_tag(tag)
                    if cleaned:
                        tags.add(cleaned)

        # If still no tags, try splitting by common separators
        if not tags:
            tag_parts = re.split(r'[,;\n]', text)
            for tag in tag_parts:
                cleaned = self._clean_tag(tag)
                if cleaned and len(cleaned) > 2:  # Minimum tag length
                    tags.add(cleaned)

        return list(tags)

    def _clean_tag(self, tag: str) -> str:
        """
        Clean and normalize a tag

        Args:
            tag: Raw tag string

        Returns:
            Cleaned tag string
        """
        # Remove quotes, brackets, and whitespace
        tag = re.sub(r'["\'\[\]]', '', tag)
        tag = tag.strip()

        # Remove special characters
        tag = re.sub(r'[^\w\s-]', '', tag)

        # Convert to lowercase and replace spaces with hyphens
        tag = tag.lower()
        tag = re.sub(r'\s+', '-', tag)

        # Remove multiple consecutive hyphens
        tag = re.sub(r'-+', '-', tag)

        # Remove leading/trailing hyphens
        tag = tag.strip('-')

        return tag


# Convenience function
def extract_tags(text: str, max_tags: int = None) -> List[str]:
    """
    Extract tags from text

    Args:
        text: Text containing tags
        max_tags: Maximum number of tags to return

    Returns:
        List of cleaned tags
    """
    tool = TagExtractionTool()
    result = tool._run(text)
    data = json.loads(result)
    tags = data["tags"]

    if max_tags:
        tags = tags[:max_tags]

    return tags
