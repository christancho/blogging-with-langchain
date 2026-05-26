"""
HTML Formatter Tool for Ghost CMS compatibility
"""
import re
from typing import Dict, Any
from langchain.tools import BaseTool


class HTMLFormatterTool(BaseTool):
    """Tool for formatting content for Ghost CMS"""

    name: str = "html_formatter"
    description: str = """
    Formats content into clean, Ghost CMS-compatible Markdown.
    Extracts title and meta description.
    Ensures proper heading hierarchy and semantic structure.
    Input should be the article content.
    Returns formatted Markdown content.
    """

    def _run(self, content: str) -> str:
        """
        Format content for Ghost CMS

        Args:
            content: Raw article content

        Returns:
            Formatted Markdown content
        """
        # Clean up the content
        formatted = self._clean_markdown(content)

        # Ensure proper heading hierarchy
        formatted = self._fix_heading_hierarchy(formatted)

        # Clean up spacing
        formatted = self._normalize_spacing(formatted)

        return formatted

    async def _arun(self, content: str) -> str:
        """Async version - falls back to sync"""
        return self._run(content)

    def _clean_markdown(self, content: str) -> str:
        """Clean and normalize Markdown syntax"""
        # Remove excessive blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Ensure consistent heading syntax (ATX-style with space)
        content = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', content, flags=re.MULTILINE)

        # Clean up list formatting
        content = re.sub(r'^\s*[-*+]\s+', '- ', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*(\d+)\.\s+', r'\1. ', content, flags=re.MULTILINE)

        # Ensure links have proper spacing
        content = re.sub(r'\]\(', '](', content)

        return content

    def _fix_heading_hierarchy(self, content: str) -> str:
        """Ensure proper heading hierarchy (single H1, proper nesting)"""
        lines = content.split('\n')
        fixed_lines = []
        h1_found = False

        for line in lines:
            # Check if line is a heading
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)

                # Ensure only one H1
                if level == 1:
                    if h1_found:
                        # Convert additional H1s to H2
                        fixed_lines.append(f'## {text}')
                    else:
                        h1_found = True
                        fixed_lines.append(line)
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)

        return '\n'.join(fixed_lines)

    def _normalize_spacing(self, content: str) -> str:
        """Normalize spacing between elements"""
        # Add blank line before headings (except at start)
        content = re.sub(r'([^\n])\n(#{1,6}\s)', r'\1\n\n\2', content)

        # Add blank line after headings
        content = re.sub(r'(#{1,6}\s.+)\n([^\n#])', r'\1\n\n\2', content)

        # Remove trailing whitespace
        lines = [line.rstrip() for line in content.split('\n')]

        # Remove excessive blank lines again
        result = '\n'.join(lines)
        result = re.sub(r'\n{3,}', '\n\n', result)

        return result.strip()

    def extract_title_and_description(self, content: str) -> Dict[str, str]:
        """
        Extract title and meta description from content

        Args:
            content: Article content

        Returns:
            Dictionary with 'title' and 'description'
        """
        title = ""
        description = ""

        # Extract first H1 as title
        h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()

        # Extract first paragraph after title as description
        # Remove title and any following blank lines
        content_after_title = content
        if h1_match:
            content_after_title = content[h1_match.end():].lstrip()

        # Get first paragraph
        para_match = re.search(r'^([^#\n].+?)(?:\n\n|\n#|$)', content_after_title, re.MULTILINE | re.DOTALL)
        if para_match:
            description = para_match.group(1).strip()
            # Remove Markdown syntax from description
            description = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', description)
            description = re.sub(r'[*_`]', '', description)
            # Truncate to reasonable length
            if len(description) > 160:
                description = description[:157] + '...'

        return {
            "title": title,
            "description": description
        }

    def markdown_to_html(self, content: str) -> str:
        """
        Convert Markdown to basic HTML

        This is a simple converter for Ghost CMS.
        For production, consider using a proper Markdown library.

        Args:
            content: Markdown content

        Returns:
            HTML content
        """
        html = content

        # Headers
        html = re.sub(r'^######\s+(.+)$', r'<h6>\1</h6>', html, flags=re.MULTILINE)
        html = re.sub(r'^#####\s+(.+)$', r'<h5>\1</h5>', html, flags=re.MULTILINE)
        html = re.sub(r'^####\s+(.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^##\s+(.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^#\s+(.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', html)

        # Paragraphs (basic)
        lines = html.split('\n')
        processed_lines = []
        in_paragraph = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_paragraph:
                    processed_lines.append('</p>')
                    in_paragraph = False
                processed_lines.append('')
            elif stripped.startswith('<h') or stripped.startswith('<ul') or stripped.startswith('<ol'):
                if in_paragraph:
                    processed_lines.append('</p>')
                    in_paragraph = False
                processed_lines.append(stripped)
            else:
                if not in_paragraph:
                    processed_lines.append('<p>')
                    in_paragraph = True
                processed_lines.append(stripped)

        if in_paragraph:
            processed_lines.append('</p>')

        html = '\n'.join(processed_lines)

        return html


# Convenience functions
def format_for_ghost(content: str) -> str:
    """Format content for Ghost CMS"""
    tool = HTMLFormatterTool()
    return tool._run(content)


def extract_metadata(content: str) -> Dict[str, str]:
    """Extract title and description from content"""
    tool = HTMLFormatterTool()
    return tool.extract_title_and_description(content)
