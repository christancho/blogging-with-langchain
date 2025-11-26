"""
Ghost CMS Tool for publishing blog posts
"""
import json
import jwt
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

from config import Config


class GhostCMSTool(BaseTool):
    """Tool for publishing content to Ghost CMS"""

    name: str = "ghost_cms_publisher"
    description: str = """
    Publishes blog posts to Ghost CMS as drafts.
    Input should be a JSON string containing:
    - title: Post title
    - content: Full post content (Markdown or HTML)
    - meta_description: SEO meta description
    - tags: List of tags
    Returns the published post ID and URL.
    """

    api_key: str = Field(default_factory=lambda: Config.GHOST_API_KEY)
    api_url: str = Field(default_factory=lambda: Config.GHOST_API_URL)
    author_id: Optional[str] = Field(default_factory=lambda: Config.GHOST_AUTHOR_ID)

    def _run(self, input_data: str) -> str:
        """
        Publish content to Ghost CMS

        Args:
            input_data: JSON string with post data

        Returns:
            JSON string with publication result
        """
        try:
            # Parse input
            data = json.loads(input_data) if isinstance(input_data, str) else input_data

            # Extract post data
            title = data.get("title", "Untitled Post")
            content = data.get("content", "")
            meta_description = data.get("meta_description", "")
            tags = data.get("tags", Config.DEFAULT_TAGS)

            # Convert Markdown to HTML if needed
            html_content = self._markdown_to_html(content)

            # Generate JWT token
            token = self._generate_jwt()

            # Prepare post data
            post_data = {
                "posts": [{
                    "title": title,
                    "html": html_content,
                    "meta_description": meta_description,
                    "tags": [{"name": tag} for tag in tags],
                    "status": "draft" if Config.PUBLISH_AS_DRAFT else "published"
                }]
            }

            # Add author if specified
            if self.author_id:
                post_data["posts"][0]["authors"] = [self.author_id]

            # Make API request
            headers = {
                "Authorization": f"Ghost {token}",
                "Content-Type": "application/json"
            }

            api_endpoint = f"{self.api_url.rstrip('/')}/ghost/api/admin/posts/"

            print(f"\n[Ghost CMS] Publishing to: {api_endpoint}")
            print(f"[Ghost CMS] Title: {title}")
            print(f"[Ghost CMS] Tags: {tags}")
            print(f"[Ghost CMS] Status: {'draft' if Config.PUBLISH_AS_DRAFT else 'published'}")

            response = requests.post(
                api_endpoint,
                headers=headers,
                json=post_data,
                timeout=30
            )

            print(f"[Ghost CMS] Response status: {response.status_code}")

            if response.status_code in [200, 201]:
                result = response.json()
                post = result.get("posts", [{}])[0]

                print(f"[Ghost CMS] ✅ Successfully published!")
                print(f"[Ghost CMS] Post ID: {post.get('id')}")
                print(f"[Ghost CMS] Post URL: {post.get('url')}")

                return json.dumps({
                    "success": True,
                    "post_id": post.get("id"),
                    "post_url": post.get("url"),
                    "status": post.get("status")
                }, indent=2)
            else:
                error_msg = response.text
                print(f"[Ghost CMS] ❌ Publication failed: {error_msg}")

                return json.dumps({
                    "success": False,
                    "error": f"HTTP {response.status_code}: {error_msg}"
                }, indent=2)

        except Exception as e:
            print(f"[Ghost CMS] ❌ Exception: {str(e)}")
            return json.dumps({
                "success": False,
                "error": str(e)
            }, indent=2)

    async def _arun(self, input_data: str) -> str:
        """Async version - falls back to sync"""
        return self._run(input_data)

    def _generate_jwt(self) -> str:
        """
        Generate JWT token for Ghost Admin API authentication

        Returns:
            JWT token string
        """
        # Split the key into ID and SECRET
        id_part, secret_part = self.api_key.split(':')

        # Prepare JWT payload
        iat = int(datetime.now().timestamp())

        payload = {
            'iat': iat,
            'exp': iat + 5 * 60,  # 5 minutes expiration
            'aud': '/admin/'
        }

        # Encode JWT
        token = jwt.encode(
            payload,
            bytes.fromhex(secret_part),
            algorithm='HS256',
            headers={'kid': id_part}
        )

        return token

    def _markdown_to_html(self, content: str) -> str:
        """
        Convert Markdown to HTML for Ghost CMS

        Note: This is a basic converter. Ghost CMS accepts Markdown in the 'mobiledoc'
        format, but HTML is simpler and more reliable.

        Args:
            content: Markdown content

        Returns:
            HTML content
        """
        import re

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
        html = re.sub(r'__(.+?)__', r'<strong>\1</strong>', html)
        html = re.sub(r'_(.+?)_', r'<em>\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', html)

        # Code blocks
        html = re.sub(r'```(\w+)?\n(.+?)\n```', r'<pre><code>\2</code></pre>', html, flags=re.DOTALL)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)

        # Lists (basic support)
        html = re.sub(r'^\s*[-*+]\s+(.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^\s*\d+\.\s+(.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

        # Wrap consecutive <li> elements in <ul>
        html = re.sub(r'(<li>.+?</li>(?:\n<li>.+?</li>)+)', r'<ul>\1</ul>', html, flags=re.DOTALL)

        # Paragraphs
        lines = html.split('\n')
        processed_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                processed_lines.append('')
            elif not any(stripped.startswith(tag) for tag in ['<h', '<ul', '<ol', '<li', '<pre', '<code']):
                processed_lines.append(f'<p>{stripped}</p>')
            else:
                processed_lines.append(stripped)

        html = '\n'.join(processed_lines)

        # Clean up multiple newlines
        html = re.sub(r'\n{3,}', '\n\n', html)

        return html


# Convenience function
def publish_to_ghost(
    title: str,
    content: str,
    meta_description: str = "",
    tags: Optional[list] = None
) -> Dict[str, Any]:
    """
    Convenience function to publish to Ghost CMS

    Args:
        title: Post title
        content: Post content (Markdown or HTML)
        meta_description: SEO meta description
        tags: List of tags

    Returns:
        Dictionary with publication result
    """
    tool = GhostCMSTool()
    input_data = {
        "title": title,
        "content": content,
        "meta_description": meta_description,
        "tags": tags or Config.DEFAULT_TAGS
    }
    result = tool._run(json.dumps(input_data))
    return json.loads(result)
