"""
Republish a saved blog post from the output folder to Ghost CMS

Usage:
    python republish.py output/blog_post_20260204_152556.md
    python republish.py output/blog_post_20260204_152556.md --status published
"""
import sys
import argparse
import re
from pathlib import Path
from tools.ghost_cms import GhostCMSTool
import json


def parse_markdown_file(file_path: str) -> dict:
    """
    Parse a saved blog post markdown file and extract metadata

    Args:
        file_path: Path to the markdown file

    Returns:
        Dictionary with title, content, meta_description, excerpt, and tags
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract metadata from the frontmatter-style header
    # Format:
    # # Title
    # **Meta Description:** ...
    # **Tags:** tag1, tag2, tag3
    # ---
    # # Title (again in content)
    # ... rest of content ...

    lines = content.split('\n')

    # Extract title (first H1)
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled Post"

    # Extract meta description
    meta_desc_match = re.search(r'\*\*Meta Description:\*\*\s*(.+?)(?:\n|$)', content)
    meta_description = meta_desc_match.group(1).strip() if meta_desc_match else ""

    # Extract tags
    tags_match = re.search(r'\*\*Tags:\*\*\s*(.+?)(?:\n|$)', content)
    if tags_match:
        tags_str = tags_match.group(1).strip()
        tags = [tag.strip() for tag in tags_str.split(',')]
    else:
        tags = []

    # Extract excerpt (first paragraph after introduction header, or first 250 chars)
    # Remove the frontmatter section (everything before ---)
    content_parts = content.split('---', 1)
    main_content = content_parts[1] if len(content_parts) > 1 else content

    # Get first meaningful paragraph for excerpt
    paragraphs = [p.strip() for p in main_content.split('\n\n') if p.strip() and not p.strip().startswith('#')]
    excerpt = ""
    if paragraphs:
        # Take first paragraph, remove markdown formatting for excerpt
        first_para = paragraphs[0]
        # Remove markdown links but keep text
        first_para = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_para)
        # Remove bold/italic
        first_para = re.sub(r'\*\*([^\*]+)\*\*', r'\1', first_para)
        first_para = re.sub(r'\*([^\*]+)\*', r'\1', first_para)
        # Truncate to 250 chars
        excerpt = first_para[:250] + "..." if len(first_para) > 250 else first_para

    return {
        "title": title,
        "content": main_content,
        "meta_description": meta_description,
        "excerpt": excerpt,
        "tags": tags
    }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Republish a saved blog post to Ghost CMS"
    )
    parser.add_argument(
        "file",
        type=str,
        help="Path to the markdown file in the output folder"
    )
    parser.add_argument(
        "--status",
        type=str,
        choices=["draft", "published"],
        default="draft",
        help="Publication status (default: draft)"
    )
    parser.add_argument(
        "--update-post-id",
        type=str,
        default=None,
        help="Ghost post ID to update (if updating existing post)"
    )

    args = parser.parse_args()

    # Check if file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ Error: File not found: {args.file}")
        sys.exit(1)

    print("\n" + "="*80)
    print("REPUBLISH TO GHOST CMS")
    print("="*80)
    print(f"File: {args.file}")
    print(f"Status: {args.status}")
    if args.update_post_id:
        print(f"Updating existing post ID: {args.update_post_id}")
    print("="*80 + "\n")

    # Parse the markdown file
    try:
        print("📖 Parsing markdown file...")
        post_data = parse_markdown_file(args.file)

        print(f"✓ Parsed successfully")
        print(f"  - Title: {post_data['title']}")
        print(f"  - Meta Description: {post_data['meta_description'][:60]}..." if len(post_data['meta_description']) > 60 else f"  - Meta Description: {post_data['meta_description']}")
        print(f"  - Tags: {', '.join(post_data['tags'])}")
        print(f"  - Excerpt length: {len(post_data['excerpt'])} chars")
        print(f"  - Content length: {len(post_data['content'])} chars")

    except Exception as e:
        print(f"❌ Error parsing file: {str(e)}")
        sys.exit(1)

    # Publish to Ghost
    try:
        print(f"\n📤 Publishing to Ghost CMS as {args.status}...")

        tool = GhostCMSTool()

        input_data = {
            "title": post_data["title"],
            "content": post_data["content"],
            "meta_description": post_data["meta_description"],
            "excerpt": post_data["excerpt"],
            "tags": post_data["tags"]
        }

        # Override the Config.PUBLISH_AS_DRAFT setting if --status is specified
        from config import Config
        original_setting = Config.PUBLISH_AS_DRAFT
        Config.PUBLISH_AS_DRAFT = (args.status == "draft")

        result_str = tool._run(json.dumps(input_data))
        result = json.loads(result_str)

        # Restore original setting
        Config.PUBLISH_AS_DRAFT = original_setting

        if result.get("success"):
            print(f"\n✅ Successfully published!")
            print(f"  - Post ID: {result.get('post_id')}")
            print(f"  - Post URL: {result.get('post_url')}")
            print(f"  - Status: {result.get('status')}")
        else:
            print(f"\n❌ Publication failed!")
            print(f"  - Error: {result.get('error')}")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error publishing: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
