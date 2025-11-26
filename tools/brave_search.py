"""
Brave Search Tool for web research
"""
import json
import requests
from typing import Any, Optional, Dict, List
from langchain.tools import BaseTool
from pydantic import Field

from config import Config


class BraveSearchTool(BaseTool):
    """Tool for performing web searches using Brave Search API"""

    name: str = "brave_search"
    description: str = """
    Performs web searches using Brave Search API.
    Input should be a search query string.
    Returns search results with titles, URLs, and descriptions.
    """

    api_key: str = Field(default_factory=lambda: Config.BRAVE_SEARCH_API_KEY)
    search_url: str = Field(default_factory=lambda: Config.BRAVE_SEARCH_URL)

    def _run(self, query: str) -> str:
        """
        Execute a web search using Brave Search API

        Args:
            query: Search query string or JSON-formatted input

        Returns:
            JSON string containing search results
        """
        # Handle JSON-formatted inputs (for compatibility with CrewAI patterns)
        actual_query = self._extract_query(query)

        try:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key
            }

            params = {
                "q": actual_query,
                "count": 10,  # Number of results
                "search_lang": "en",
                "safesearch": "moderate"
            }

            response = requests.get(
                self.search_url,
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            results = self._format_results(data)

            return json.dumps(results, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"Search failed: {str(e)}",
                "query": actual_query,
                "results": []
            })

    async def _arun(self, query: str) -> str:
        """Async version - not implemented, falls back to sync"""
        return self._run(query)

    def _extract_query(self, input_text: str) -> str:
        """
        Extract actual search query from various input formats

        Handles:
        - Plain text: "python programming"
        - JSON: {"query": "python programming"}
        - Complex JSON from agent outputs
        """
        # Try to parse as JSON first
        try:
            data = json.loads(input_text)
            if isinstance(data, dict):
                # Look for common query field names
                for key in ["query", "search_query", "q", "search", "topic"]:
                    if key in data:
                        return str(data[key])
                # If no recognized key, convert dict to string
                return str(data)
            return str(data)
        except (json.JSONDecodeError, TypeError):
            # Not JSON, treat as plain text
            return input_text.strip()

    def _format_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Brave Search API response into structured results

        Args:
            data: Raw API response

        Returns:
            Formatted results dictionary
        """
        web_results = data.get("web", {}).get("results", [])

        formatted_results = []
        for result in web_results[:10]:  # Top 10 results
            formatted_results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("description", ""),
                "published": result.get("page_age", "")
            })

        return {
            "query": data.get("query", {}).get("original", ""),
            "results_count": len(formatted_results),
            "results": formatted_results
        }


# Convenience function for direct use
def search_web(query: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to perform a web search

    Args:
        query: Search query
        api_key: Optional API key (uses config default if not provided)

    Returns:
        Dictionary of search results
    """
    tool = BraveSearchTool(api_key=api_key or Config.BRAVE_SEARCH_API_KEY)
    result = tool._run(query)
    return json.loads(result)
