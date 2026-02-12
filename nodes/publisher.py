"""
Ghost CMS publisher node
"""
import json
import requests
from datetime import datetime
from typing import Dict, Any

from state import BlogState
from config import Config
from tools import GhostCMSTool


def publisher_node(state: BlogState) -> Dict[str, Any]:
    """
    Publisher node: Publish article to Ghost CMS

    Args:
        state: Current blog state

    Returns:
        Partial state update with publication results
    """
    print("\n" + "="*80)
    print("PUBLISHER NODE")
    print("="*80)

    final_content = state.get("final_content", "")
    seo_title = state.get("seo_title", state.get("article_title", ""))
    meta_description = state.get("meta_description", "")
    excerpt = state.get("excerpt", "")
    tags = state.get("tags", Config.DEFAULT_TAGS)
    forced_publish_note = state.get("forced_publish_note", "")

    print(f"Publishing to Ghost CMS")
    print(f"  - Title: {seo_title}")
    print(f"  - Excerpt: {excerpt[:80]}..." if excerpt else "  - Excerpt: (empty)")
    print(f"  - Tags: {tags}")
    print(f"  - Status: {'draft' if Config.PUBLISH_AS_DRAFT else 'published'}")
    if forced_publish_note:
        print(f"  - ⚠️  FORCED PUBLISH (max revisions exceeded)")

    # Prepend forced publish note if max revisions exceeded
    content_to_publish = final_content
    if forced_publish_note:
        content_to_publish = forced_publish_note + content_to_publish

    # Save to local file first
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{Config.OUTPUT_DIR}/blog_post_{timestamp}.md"

    try:
        # Ensure output directory exists
        import os
        os.makedirs(Config.OUTPUT_DIR, exist_ok=True)

        # Save to file
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(f"# {seo_title}\n\n")
            f.write(f"**Meta Description:** {meta_description}\n\n")
            f.write(f"**Tags:** {', '.join(tags)}\n\n")
            f.write("---\n\n")
            f.write(content_to_publish)

        print(f"\n✓ Saved locally: {output_filename}")

    except Exception as e:
        print(f"\n✗ Failed to save locally: {str(e)}")

    # Publish to Ghost CMS
    ghost_tool = GhostCMSTool()

    # Remove H1 title from content to avoid duplication in Ghost CMS
    # (title is sent separately, content shouldn't include it)
    import re
    content_without_title = re.sub(
        r'^#\s+.+?(?:\n\n|\n(?=#))',
        '',
        content_to_publish,
        count=1,
        flags=re.MULTILINE
    ).strip()

    post_data = {
        "title": seo_title,
        "content": content_without_title,
        "meta_description": meta_description,
        "excerpt": excerpt,
        "tags": tags
    }

    try:
        result = ghost_tool._run(json.dumps(post_data))
        result_data = json.loads(result)

        if result_data.get("success"):
            print(f"\n✓ Successfully published to Ghost CMS")

            # Call webhook if enabled
            if Config.WEBHOOK_ENABLED and Config.WEBHOOK_URL:
                try:
                    _call_webhook(
                        title=seo_title,
                        url=result_data.get("post_url", ""),
                        excerpt=excerpt,
                        tags=tags,
                        content_preview=content_without_title[:500]
                    )
                except Exception as e:
                    print(f"\n⚠️  Webhook notification failed: {str(e)}")
                    # Don't fail the whole publish if webhook fails

            return {
                "ghost_post_id": result_data.get("post_id"),
                "ghost_post_url": result_data.get("post_url"),
                "publication_status": result_data.get("status", "draft"),
                "timestamp": datetime.now().isoformat()
            }
        else:
            error_msg = result_data.get("error", "Unknown error")
            print(f"\n✗ Publication failed: {error_msg}")

            return {
                "ghost_post_id": None,
                "ghost_post_url": None,
                "publication_status": "failed",
                "timestamp": datetime.now().isoformat(),
                "errors": state.get("errors", []) + [f"Publication error: {error_msg}"]
            }

    except Exception as e:
        print(f"\n✗ Publisher exception: {str(e)}")

        return {
            "ghost_post_id": None,
            "ghost_post_url": None,
            "publication_status": "failed",
            "timestamp": datetime.now().isoformat(),
            "errors": state.get("errors", []) + [f"Publisher exception: {str(e)}"]
        }


def _call_webhook(title: str, url: str, excerpt: str, tags: list, content_preview: str) -> None:
    """
    Call the Cloudflare Worker webhook to send email notification

    Args:
        title: Blog post title
        url: Blog post URL
        excerpt: Blog post excerpt
        tags: Blog post tags
        content_preview: First 500 chars of content
    """
    print(f"\n📧 Sending webhook notification to {Config.WEBHOOK_URL}")

    payload = {
        "title": title,
        "url": url,
        "excerpt": excerpt,
        "tags": tags,
        "content_preview": content_preview
    }

    try:
        response = requests.post(
            Config.WEBHOOK_URL,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            print("✓ Webhook notification sent successfully")
            print(f"  Response: {response.json()}")
        else:
            print(f"✗ Webhook returned status {response.status_code}")
            print(f"  Response: {response.text}")
            raise Exception(f"Webhook returned status {response.status_code}")

    except requests.exceptions.Timeout:
        print("✗ Webhook request timed out after 30 seconds")
        raise Exception("Webhook timeout")
    except requests.exceptions.RequestException as e:
        print(f"✗ Webhook request failed: {str(e)}")
        raise
