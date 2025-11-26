"""
SEO Analysis Tool for content optimization
"""
import re
from typing import Dict, List, Any
from langchain.tools import BaseTool

from config import Config


class SEOAnalysisTool(BaseTool):
    """Tool for analyzing content SEO metrics"""

    name: str = "seo_analyzer"
    description: str = """
    Analyzes content for SEO optimization.
    Checks keyword density, header structure, meta descriptions, and word count.
    Input should be the article content as a string.
    Returns a JSON string with SEO analysis and recommendations.
    """

    def _run(self, content: str) -> str:
        """
        Analyze content for SEO metrics

        Args:
            content: Article content to analyze

        Returns:
            JSON string with SEO analysis
        """
        analysis = {
            "word_count": self._count_words(content),
            "headers": self._analyze_headers(content),
            "keyword_density": self._analyze_keyword_density(content),
            "readability": self._calculate_readability(content),
            "issues": [],
            "recommendations": []
        }

        # Check for issues
        if not analysis["headers"].get("h1_count"):
            analysis["issues"].append("Missing H1 header")

        if analysis["word_count"] < Config.WORD_COUNT_TARGET:
            analysis["issues"].append(
                f"Word count ({analysis['word_count']}) below target ({Config.WORD_COUNT_TARGET})"
            )

        # Generate recommendations
        if analysis["word_count"] >= Config.WORD_COUNT_TARGET:
            analysis["recommendations"].append("Good word count for SEO")

        if analysis["headers"]["h2_count"] >= 4:
            analysis["recommendations"].append("Good use of H2 headers for structure")

        import json
        return json.dumps(analysis, indent=2)

    async def _arun(self, content: str) -> str:
        """Async version - falls back to sync"""
        return self._run(content)

    def _count_words(self, content: str) -> int:
        """Count words in content"""
        # Remove HTML/Markdown tags for accurate count
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        words = text.split()
        return len(words)

    def _analyze_headers(self, content: str) -> Dict[str, int]:
        """Analyze header structure"""
        headers = {
            "h1_count": len(re.findall(r'^#\s+', content, re.MULTILINE)),
            "h2_count": len(re.findall(r'^##\s+', content, re.MULTILINE)),
            "h3_count": len(re.findall(r'^###\s+', content, re.MULTILINE)),
            "h4_count": len(re.findall(r'^####\s+', content, re.MULTILINE)),
        }

        # Also check HTML headers
        headers["h1_count"] += len(re.findall(r'<h1[^>]*>', content, re.IGNORECASE))
        headers["h2_count"] += len(re.findall(r'<h2[^>]*>', content, re.IGNORECASE))
        headers["h3_count"] += len(re.findall(r'<h3[^>]*>', content, re.IGNORECASE))

        return headers

    def _analyze_keyword_density(self, content: str) -> Dict[str, Any]:
        """Analyze keyword density and distribution"""
        # Remove HTML/Markdown
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Convert to lowercase for analysis
        text_lower = text.lower()
        words = text_lower.split()

        if not words:
            return {"top_keywords": [], "avg_density": 0.0}

        # Count word frequency (excluding common stop words)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
            'can', 'could', 'may', 'might', 'must', 'this', 'that', 'these', 'those'
        }

        word_freq = {}
        for word in words:
            # Clean word
            word = re.sub(r'[^\w]', '', word)
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

        # Get top keywords
        top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]

        # Calculate densities
        total_words = len(words)
        keyword_data = [
            {
                "keyword": word,
                "count": count,
                "density": round((count / total_words) * 100, 2)
            }
            for word, count in top_keywords
        ]

        return {
            "top_keywords": keyword_data,
            "avg_density": round(sum(k["density"] for k in keyword_data) / len(keyword_data), 2) if keyword_data else 0.0
        }

    def _calculate_readability(self, content: str) -> Dict[str, Any]:
        """Calculate basic readability metrics"""
        # Remove HTML/Markdown
        text = re.sub(r'<[^>]+>', '', content)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Count words
        words = text.split()

        if not sentences or not words:
            return {
                "avg_sentence_length": 0,
                "avg_word_length": 0
            }

        # Calculate metrics
        avg_sentence_length = len(words) / len(sentences)

        # Average word length
        total_chars = sum(len(word) for word in words)
        avg_word_length = total_chars / len(words) if words else 0

        return {
            "avg_sentence_length": round(avg_sentence_length, 1),
            "avg_word_length": round(avg_word_length, 1),
            "total_sentences": len(sentences)
        }


# Convenience function
def analyze_seo(content: str) -> Dict[str, Any]:
    """
    Convenience function to analyze content SEO

    Args:
        content: Content to analyze

    Returns:
        Dictionary with SEO analysis
    """
    import json
    tool = SEOAnalysisTool()
    result = tool._run(content)
    return json.loads(result)
