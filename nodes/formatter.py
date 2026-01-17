"""
HTML formatter node for Ghost CMS compatibility
"""
import re
from typing import Dict, Any, List, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from nodes.prompt_loader import PromptLoader
from tools import HTMLFormatterTool


def extract_headings(content: str) -> List[Tuple[str, int, str]]:
    """
    Extract headings from markdown content, excluding code blocks.

    Args:
        content: Markdown content to parse

    Returns:
        List of tuples: (heading_text, level, anchor_id)
        where level is 2 for H2 or 3 for H3
    """
    headings = []
    in_code_block = False

    # Find all H2 and H3 headings, skipping code blocks
    lines = content.split('\n')
    for line in lines:
        # Track code blocks (``` or ~~~ fences)
        if re.match(r'^```', line) or re.match(r'^~~~', line):
            in_code_block = not in_code_block
            continue

        # Skip lines inside code blocks
        if in_code_block:
            continue

        h2_match = re.match(r'^##\s+(.+)$', line)
        h3_match = re.match(r'^###\s+(.+)$', line)

        if h2_match:
            text = h2_match.group(1).strip()
            anchor = text.lower().replace(' ', '-').replace('?', '').replace('!', '').replace(',', '')
            headings.append((text, 2, anchor))
        elif h3_match and Config.TOC_INCLUDE_H3:
            text = h3_match.group(1).strip()
            anchor = text.lower().replace(' ', '-').replace('?', '').replace('!', '').replace(',', '')
            headings.append((text, 3, anchor))

    return headings


def generate_table_of_contents(headings: List[Tuple[str, int, str]]) -> str:
    """
    Generate markdown table of contents from headings.

    Args:
        headings: List of tuples from extract_headings()

    Returns:
        Markdown-formatted table of contents
    """
    if not headings or len(headings) < Config.TOC_MIN_SECTIONS:
        return ""

    toc_lines = ["## Table of Contents\n"]

    for text, level, anchor in headings:
        if level == 2:
            toc_lines.append(f"- [{text}](#{anchor})")
        elif level == 3:
            toc_lines.append(f"  - [{text}](#{anchor})")

    return "\n".join(toc_lines) + "\n"


def insert_table_of_contents(content: str, toc: str) -> str:
    """
    Insert table of contents after the introduction section (after first H2).

    Args:
        content: Full markdown content
        toc: Generated table of contents markdown

    Returns:
        Content with TOC inserted
    """
    if not toc:
        return content

    lines = content.split('\n')
    h2_indices = []

    # Find all H2 headings
    for i, line in enumerate(lines):
        if re.match(r'^##\s+', line):
            h2_indices.append(i)

    # Insert TOC before the second H2 (after introduction section)
    if len(h2_indices) >= 2:
        insert_pos = h2_indices[1]
        # Skip back over any blank lines before the second H2
        while insert_pos > 0 and lines[insert_pos - 1].strip() == '':
            insert_pos -= 1

        lines.insert(insert_pos, toc)
        return '\n'.join(lines)

    # Fallback: if not enough H2 headings, insert after H1 title
    for i, line in enumerate(lines):
        if re.match(r'^#\s+', line):
            insert_pos = i + 1
            if insert_pos < len(lines) and lines[insert_pos].strip() == '':
                insert_pos += 1
            lines.insert(insert_pos, toc)
            return '\n'.join(lines)

    return content


def formatter_node(state: BlogState) -> Dict[str, Any]:
    """
    Formatter node: Format content for Ghost CMS

    Args:
        state: Current blog state

    Returns:
        Partial state update with formatted content
    """
    print("\n" + "="*80)
    print("FORMATTER NODE")
    print("="*80)

    article_content = state.get("article_content", "")
    seo_metadata = state.get("seo_metadata", {})
    seo_title = state.get("seo_title", "")

    print(f"Formatting article for Ghost CMS")

    # Initialize LLM
    llm = Config.get_llm()

    # Escape curly braces in article content and metadata to prevent ChatPromptTemplate
    # from interpreting them as template variables
    article_content_escaped = article_content.replace("{", "{{").replace("}", "}}")
    seo_metadata_escaped = str(seo_metadata).replace("{", "{{").replace("}", "}}")

    # Create prompt
    formatter_template = PromptLoader.load("formatter")
    formatter_prompt = formatter_template.render(
        article_content=article_content_escaped,
        seo_metadata=seo_metadata_escaped
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", formatter_prompt),
        ("human", "Format the article now.")
    ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Format content
    try:
        formatted_content = chain.invoke({})

        # Use HTMLFormatterTool for additional cleanup
        formatter_tool = HTMLFormatterTool()
        formatted_content = formatter_tool._run(formatted_content)

        # Replace first H1 with SEO title if provided
        if seo_title:
            formatted_content = re.sub(
                r'^#\s+.+$',
                f'# {seo_title}',
                formatted_content,
                count=1,
                flags=re.MULTILINE
            )

        # Generate and insert table of contents if enabled
        table_of_contents = ""
        if Config.INCLUDE_TABLE_OF_CONTENTS:
            headings = extract_headings(formatted_content)
            table_of_contents = generate_table_of_contents(headings)
            if table_of_contents:
                formatted_content = insert_table_of_contents(formatted_content, table_of_contents)
                print(f"  - Table of Contents added ({len(headings)} sections)")

        # Generate HTML version
        formatted_html = formatter_tool.markdown_to_html(formatted_content)

        print(f"\n✓ Formatting completed")
        print(f"  - Markdown length: {len(formatted_content)} chars")
        print(f"  - HTML length: {len(formatted_html)} chars")

        return {
            "formatted_content": formatted_content,
            "formatted_html": formatted_html,
            "table_of_contents": table_of_contents
        }

    except Exception as e:
        print(f"\n✗ Formatting failed: {str(e)}")
        # Return original content as fallback
        return {
            "formatted_content": article_content,
            "formatted_html": article_content,
            "errors": state.get("errors", []) + [f"Formatting error: {str(e)}"]
        }
