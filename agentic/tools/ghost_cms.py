"""
Ghost CMS Tool for publishing blog posts
"""
import json
import jwt
import requests
import markdown
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
    - excerpt: Article excerpt for listing pages (optional)
    - tags: List of tags
    - codeinjection_head: Custom code for <head> section (optional)
    - codeinjection_foot: Custom code before </body> (optional)

    Features:
    - Automatically preserves language identifiers in code blocks (e.g., ```python)
    - Auto-injects Prism.js for syntax highlighting when code blocks are detected

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
            excerpt = data.get("excerpt", "")
            tags = data.get("tags", Config.DEFAULT_TAGS)
            codeinjection_head = data.get("codeinjection_head", "")
            codeinjection_foot = data.get("codeinjection_foot", "")

            # Validate and truncate excerpt to Ghost's 300 character limit
            if excerpt and len(excerpt) > 300:
                print(f"[Ghost CMS] Warning: Excerpt truncated from {len(excerpt)} to 300 chars")
                excerpt = excerpt[:297] + "..."

            # Convert Markdown to HTML if needed
            html_content = self._markdown_to_html(content)

            # Auto-inject Prism.js for syntax highlighting if code blocks are present
            if not codeinjection_head and ('<code class="language-' in html_content or '<pre><code>' in html_content):
                codeinjection_head = '''<script src="https://cdn.jsdelivr.net/npm/prismjs/prism.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/prismjs/plugins/autoloader/prism-autoloader.min.js" defer></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/prismjs/themes/prism.min.css">'''

            # Generate JWT token
            token = self._generate_jwt()

            # Prepare post data
            post_data = {
                "posts": [{
                    "title": title,
                    "html": html_content,
                    "meta_description": meta_description,
                    "custom_excerpt": excerpt,
                    "tags": [{"name": tag} for tag in tags],
                    "status": "draft" if Config.PUBLISH_AS_DRAFT else "published"
                }]
            }

            # Add code injection if present
            if codeinjection_head:
                post_data["posts"][0]["codeinjection_head"] = codeinjection_head
            if codeinjection_foot:
                post_data["posts"][0]["codeinjection_foot"] = codeinjection_foot

            # Add author if specified
            if self.author_id:
                post_data["posts"][0]["authors"] = [self.author_id]

            # Make API request
            headers = {
                "Authorization": f"Ghost {token}",
                "Content-Type": "application/json"
            }

            api_endpoint = f"{self.api_url.rstrip('/')}/ghost/api/admin/posts/?source=html"

            print(f"\n[Ghost CMS] Publishing to: {api_endpoint}")
            print(f"[Ghost CMS] Title: {title}")
            print(f"[Ghost CMS] Meta Description: {meta_description[:80]}..." if len(meta_description) > 80 else f"[Ghost CMS] Meta Description: {meta_description}")
            print(f"[Ghost CMS] Excerpt: {excerpt[:80]}..." if len(excerpt) > 80 else f"[Ghost CMS] Excerpt: {excerpt}")
            print(f"[Ghost CMS] Excerpt length: {len(excerpt)} chars")
            print(f"[Ghost CMS] Tags: {tags}")
            print(f"[Ghost CMS] Status: {'draft' if Config.PUBLISH_AS_DRAFT else 'published'}")
            if codeinjection_head:
                print(f"[Ghost CMS] Code Injection: Prism.js syntax highlighting enabled")

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
        Convert Markdown to HTML for Ghost CMS using the markdown library

        Args:
            content: Markdown content

        Returns:
            HTML content
        """
        import re

        # Pre-process: Add blank lines before lists if they don't exist
        # This ensures the markdown library recognizes them as proper lists
        lines = content.split('\n')
        processed_lines = []

        for i, line in enumerate(lines):
            # Check if this line starts a list (unordered or ordered)
            is_list_item = (
                re.match(r'^\s*[-*+]\s+', line) or  # Unordered list
                re.match(r'^\s*\d+\.\s+', line)      # Ordered list
            )

            if is_list_item and i > 0:
                prev_line = lines[i-1].strip()
                # Add blank line before list if previous line isn't blank and isn't a list item
                if prev_line and not re.match(r'^\s*[-*+]\s+', lines[i-1]) and not re.match(r'^\s*\d+\.\s+', lines[i-1]):
                    processed_lines.append('')

            processed_lines.append(line)

        preprocessed_content = '\n'.join(processed_lines)

        # Use the markdown library with standard extensions
        # The 'extra' extension includes: fenced_code, tables, attr_list, def_list, etc.
        html = markdown.markdown(
            preprocessed_content,
            extensions=['extra', 'sane_lists']
        )

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
