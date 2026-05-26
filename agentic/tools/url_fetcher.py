"""
URL Fetcher Tool for fetching content from web pages and GitHub repositories
"""
import re
import subprocess
import json
from typing import Dict, List, Optional
from urllib.parse import urlparse


class URLFetcherTool:
    """
    Tool for fetching content from URLs mentioned in instructions.
    Handles both general web pages and GitHub repositories with special handling.
    """

    def fetch_url_content(self, url: str) -> Dict[str, str]:
        """
        Fetch content from a URL.

        Args:
            url: The URL to fetch content from

        Returns:
            Dictionary with 'url', 'content', 'type', and 'error' keys
        """
        try:
            # Check if it's a GitHub URL
            if self._is_github_url(url):
                return self._fetch_github_content(url)
            else:
                return self._fetch_web_content(url)
        except Exception as e:
            return {
                "url": url,
                "content": "",
                "type": "error",
                "error": str(e)
            }

    def _is_github_url(self, url: str) -> bool:
        """Check if URL is a GitHub repository URL"""
        parsed = urlparse(url)
        return parsed.netloc in ['github.com', 'www.github.com']

    def _fetch_github_content(self, url: str) -> Dict[str, str]:
        """
        Fetch content from a GitHub repository using gh CLI.
        Falls back to web fetching if gh CLI is not available.

        Args:
            url: GitHub repository URL

        Returns:
            Dictionary with repository information
        """
        try:
            # Extract owner and repo from URL
            # Format: https://github.com/owner/repo
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')

            if len(path_parts) < 2:
                return self._fetch_web_content(url)

            owner = path_parts[0]
            repo = path_parts[1]

            # Try to use gh CLI to fetch README
            try:
                # Get repository metadata
                repo_result = subprocess.run(
                    ['gh', 'repo', 'view', f'{owner}/{repo}', '--json', 'name,description,url'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if repo_result.returncode == 0:
                    repo_data = json.loads(repo_result.stdout)

                    # Get README content separately using gh api
                    readme_result = subprocess.run(
                        ['gh', 'api', f'repos/{owner}/{repo}/readme', '-H', 'Accept: application/vnd.github.raw'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    readme_content = readme_result.stdout if readme_result.returncode == 0 else "No README available"

                    # Get repository file tree to understand structure
                    tree_result = subprocess.run(
                        ['gh', 'api', f'repos/{owner}/{repo}/git/trees/main?recursive=1'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    tree_content = ""
                    if tree_result.returncode == 0:
                        tree_data = json.loads(tree_result.stdout)
                        # List key files and directories
                        files = [item['path'] for item in tree_data.get('tree', [])[:50]]  # Limit to first 50
                        tree_content = "\n\n### Repository Structure:\n" + "\n".join(f"- {f}" for f in files)

                    content = f"""# GitHub Repository: {repo_data.get('name', repo)}

**URL:** {repo_data.get('url', url)}
**Description:** {repo_data.get('description', 'No description provided')}

## README Content:

{readme_content}
{tree_content}
"""

                    return {
                        "url": url,
                        "content": content,
                        "type": "github",
                        "error": None
                    }
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
                print(f"  ℹ gh CLI unavailable or failed ({e}), falling back to web fetch")
                pass

            # Fallback to web fetching
            return self._fetch_web_content(url)

        except Exception as e:
            return {
                "url": url,
                "content": "",
                "type": "github_error",
                "error": str(e)
            }

    def _fetch_web_content(self, url: str) -> Dict[str, str]:
        """
        Fetch content from a general web page using curl.

        Args:
            url: Web page URL

        Returns:
            Dictionary with page content
        """
        try:
            # Use curl to fetch the page
            result = subprocess.run(
                ['curl', '-L', '-s', '--max-time', '30', url],
                capture_output=True,
                text=True,
                timeout=35
            )

            if result.returncode == 0 and result.stdout:
                # Basic HTML to text conversion
                content = self._extract_text_from_html(result.stdout)

                return {
                    "url": url,
                    "content": content[:10000],  # Limit to 10k chars to avoid overwhelming context
                    "type": "web",
                    "error": None
                }
            else:
                return {
                    "url": url,
                    "content": "",
                    "type": "web_error",
                    "error": f"Failed to fetch: HTTP error or timeout"
                }

        except Exception as e:
            return {
                "url": url,
                "content": "",
                "type": "web_error",
                "error": str(e)
            }

    def _extract_text_from_html(self, html: str) -> str:
        """
        Extract readable text from HTML content.
        This is a simple implementation that removes common HTML tags.

        Args:
            html: HTML content

        Returns:
            Extracted text content
        """
        # Remove script and style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

        # Replace common block tags with newlines
        text = re.sub(r'</?(div|p|br|h[1-6]|li|tr)[^>]*>', '\n', text, flags=re.IGNORECASE)

        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = text.replace('&quot;', '"')

        # Clean up whitespace
        text = re.sub(r'\n\s*\n+', '\n\n', text)  # Multiple blank lines to double newline
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space

        return text.strip()

    def extract_urls_from_text(self, text: str) -> List[str]:
        """
        Extract URLs from text using regex.

        Args:
            text: Text to extract URLs from

        Returns:
            List of URLs found
        """
        # Pattern to match HTTP/HTTPS URLs
        url_pattern = r'https?://[^\s\)\]\"\'\,]+'
        urls = re.findall(url_pattern, text)

        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls
