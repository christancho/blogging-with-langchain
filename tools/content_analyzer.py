"""
Content Analysis Tool for quality assessment
"""
import re
import json
from typing import Dict, Any, List
from langchain.tools import BaseTool

from config import Config


class ContentAnalysisTool(BaseTool):
    """Tool for analyzing content quality and metrics"""

    name: str = "content_analyzer"
    description: str = """
    Analyzes content quality through various metrics including:
    - Word and sentence counts
    - Readability scores
    - Technical terminology detection
    - Code block presence
    - Link analysis
    Input should be the article content.
    Returns a JSON string with quality metrics.
    """

    def _run(self, content: str) -> str:
        """
        Analyze content quality

        Args:
            content: Article content to analyze

        Returns:
            JSON string with analysis results
        """
        analysis = {
            "word_count": self._count_words(content),
            "sentence_count": self._count_sentences(content),
            "paragraph_count": self._count_paragraphs(content),
            "readability": self._analyze_readability(content),
            "links": self._analyze_links(content),
            "technical_terms": self._detect_technical_terms(content),
            "code_blocks": self._detect_code_blocks(content),
            "structure": self._analyze_structure(content),
            "quality_score": 0.0
        }

        # Calculate overall quality score
        analysis["quality_score"] = self._calculate_quality_score(analysis)

        return json.dumps(analysis, indent=2)

    async def _arun(self, content: str) -> str:
        """Async version - falls back to sync"""
        return self._run(content)

    def _count_words(self, content: str) -> int:
        """Count words in content"""
        # Remove HTML/Markdown tags
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        words = text.split()
        return len(words)

    def _count_sentences(self, content: str) -> int:
        """Count sentences in content"""
        # Remove HTML/Markdown
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Split by sentence endings
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        return len(sentences)

    def _count_paragraphs(self, content: str) -> int:
        """Count paragraphs in content"""
        # Split by double newlines
        paragraphs = re.split(r'\n\s*\n', content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        # Filter out headings and very short paragraphs
        paragraphs = [
            p for p in paragraphs
            if not p.startswith('#') and len(p.split()) > 5
        ]

        return len(paragraphs)

    def _analyze_readability(self, content: str) -> Dict[str, Any]:
        """Calculate readability metrics"""
        # Remove HTML/Markdown
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        words = text.split()
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences or not words:
            return {
                "avg_sentence_length": 0,
                "avg_word_length": 0,
                "complex_words_ratio": 0.0
            }

        # Average sentence length
        avg_sentence_length = len(words) / len(sentences)

        # Average word length
        total_chars = sum(len(word) for word in words)
        avg_word_length = total_chars / len(words) if words else 0

        # Complex words (> 12 characters)
        complex_words = sum(1 for word in words if len(word) > 12)
        complex_words_ratio = complex_words / len(words) if words else 0

        return {
            "avg_sentence_length": round(avg_sentence_length, 1),
            "avg_word_length": round(avg_word_length, 1),
            "complex_words_ratio": round(complex_words_ratio, 3)
        }

    def _analyze_links(self, content: str) -> Dict[str, Any]:
        """Analyze links in content"""
        # Find Markdown links
        md_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', content)

        # Find HTML links
        html_links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', content, re.IGNORECASE)

        total_links = len(md_links) + len(html_links)

        # Extract URLs
        urls = [url for _, url in md_links] + [url for url, _ in html_links]

        # Count external vs internal
        external_links = sum(1 for url in urls if url.startswith('http'))
        internal_links = total_links - external_links

        return {
            "total_links": total_links,
            "markdown_links": len(md_links),
            "html_links": len(html_links),
            "external_links": external_links,
            "internal_links": internal_links,
            "meets_minimum": total_links >= Config.MIN_INLINE_LINKS
        }

    def _detect_technical_terms(self, content: str) -> Dict[str, Any]:
        """Detect technical terminology"""
        # Common technical term patterns
        technical_patterns = [
            r'\bAPI\b', r'\bSDK\b', r'\bCLI\b', r'\bREST\b', r'\bJSON\b',
            r'\bHTTP[S]?\b', r'\bSQL\b', r'\bNoSQL\b', r'\bML\b', r'\bAI\b',
            r'\b[A-Z]{2,}\b',  # Acronyms
            r'\b\w+\(\)',  # Function calls
            r'\b\w+\.\w+',  # Dotted notation
        ]

        matches = 0
        for pattern in technical_patterns:
            matches += len(re.findall(pattern, content))

        word_count = self._count_words(content)
        tech_density = matches / word_count if word_count > 0 else 0

        return {
            "technical_term_count": matches,
            "technical_density": round(tech_density, 3),
            "is_technical": tech_density > 0.02  # 2% threshold
        }

    def _detect_code_blocks(self, content: str) -> Dict[str, Any]:
        """Detect code blocks and inline code"""
        # Code blocks (```)
        code_blocks = re.findall(r'```[\w]*\n(.+?)\n```', content, re.DOTALL)

        # Inline code (`)
        inline_code = re.findall(r'`([^`]+)`', content)

        return {
            "code_block_count": len(code_blocks),
            "inline_code_count": len(inline_code),
            "has_code": len(code_blocks) > 0 or len(inline_code) > 0
        }

    def _analyze_structure(self, content: str) -> Dict[str, Any]:
        """Analyze document structure"""
        # Count headings
        h1_count = len(re.findall(r'^#\s+', content, re.MULTILINE))
        h2_count = len(re.findall(r'^##\s+', content, re.MULTILINE))
        h3_count = len(re.findall(r'^###\s+', content, re.MULTILINE))

        # Check for intro and conclusion
        has_intro = bool(re.search(r'(?i)(introduction|overview)', content[:500]))
        has_conclusion = bool(re.search(r'(?i)(conclusion|summary|final thoughts)', content[-500:]))

        return {
            "h1_count": h1_count,
            "h2_count": h2_count,
            "h3_count": h3_count,
            "has_intro": has_intro,
            "has_conclusion": has_conclusion,
            "well_structured": h1_count == 1 and h2_count >= Config.NUM_SECTIONS
        }

    def _calculate_quality_score(self, analysis: Dict[str, Any]) -> float:
        """
        Calculate overall quality score (0-1)

        Factors:
        - Word count meets target
        - Has minimum links
        - Well structured
        - Good readability
        """
        score = 0.0
        max_score = 0.0

        # Word count (25 points)
        max_score += 0.25
        if analysis["word_count"] >= Config.WORD_COUNT_TARGET:
            score += 0.25
        else:
            score += 0.25 * (analysis["word_count"] / Config.WORD_COUNT_TARGET)

        # Links (25 points)
        max_score += 0.25
        if analysis["links"]["meets_minimum"]:
            score += 0.25
        else:
            ratio = analysis["links"]["total_links"] / Config.MIN_INLINE_LINKS
            score += 0.25 * min(ratio, 1.0)

        # Structure (25 points)
        max_score += 0.25
        if analysis["structure"]["well_structured"]:
            score += 0.25
        else:
            # Partial credit
            if analysis["structure"]["h1_count"] == 1:
                score += 0.1
            if analysis["structure"]["h2_count"] >= 3:
                score += 0.15

        # Readability (25 points)
        max_score += 0.25
        readability = analysis["readability"]
        # Ideal: 15-20 words per sentence, 5-6 chars per word
        sentence_score = 1.0 - abs(readability["avg_sentence_length"] - 17.5) / 17.5
        word_score = 1.0 - abs(readability["avg_word_length"] - 5.5) / 5.5
        score += 0.25 * max(0, (sentence_score + word_score) / 2)

        return round(score / max_score, 2) if max_score > 0 else 0.0


# Convenience function
def analyze_content(content: str) -> Dict[str, Any]:
    """
    Analyze content quality

    Args:
        content: Content to analyze

    Returns:
        Dictionary with quality metrics
    """
    tool = ContentAnalysisTool()
    result = tool._run(content)
    return json.loads(result)
