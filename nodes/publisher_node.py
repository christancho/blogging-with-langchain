"""
Ghost CMS publisher node
"""
import json
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

    print(f"Publishing to Ghost CMS")
    print(f"  - Title: {seo_title}")
    print(f"  - Excerpt: {excerpt[:80]}..." if excerpt else "  - Excerpt: (empty)")
    print(f"  - Tags: {tags}")
    print(f"  - Status: {'draft' if Config.PUBLISH_AS_DRAFT else 'published'}")

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
            f.write(final_content)

        print(f"\n✓ Saved locally: {output_filename}")

    except Exception as e:
        print(f"\n✗ Failed to save locally: {str(e)}")

    # Publish to Ghost CMS
    ghost_tool = GhostCMSTool()

    post_data = {
        "title": seo_title,
        "content": final_content,
        "meta_description": meta_description,
        "excerpt": excerpt,
        "tags": tags
    }

    try:
        result = ghost_tool._run(json.dumps(post_data))
        result_data = json.loads(result)

        if result_data.get("success"):
            print(f"\n✓ Successfully published to Ghost CMS")

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
