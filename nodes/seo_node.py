"""
SEO optimization node
"""
import re
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from prompts import SEO_PROMPT
from tools import TagExtractionTool


def seo_node(state: BlogState) -> Dict[str, Any]:
    """
    SEO node: Optimize article for search engines

    Args:
        state: Current blog state

    Returns:
        Partial state update with SEO metadata
    """
    print("\n" + "="*80)
    print("SEO NODE")
    print("="*80)

    article_title = state.get("article_title", "")
    article_content = state.get("article_content", "")

    print(f"Optimizing article: {article_title}")

    # Initialize LLM
    llm = Config.get_llm()

    # Create prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", SEO_PROMPT),
        ("human", "Perform SEO optimization now.")
    ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Generate SEO metadata
    try:
        seo_output = chain.invoke({
            "article_title": article_title,
            "article_content": article_content
        })

        # Parse SEO output
        seo_data = parse_seo_output(seo_output)

        print(f"\n✓ SEO optimization completed")
        print(f"  - SEO Title: {seo_data['seo_title']}")
        print(f"  - Meta description length: {len(seo_data['meta_description'])} chars")
        print(f"  - Tags: {len(seo_data['tags'])}")
        print(f"  - Keywords: {len(seo_data['keywords'])}")

        return {
            "seo_metadata": seo_data,
            "seo_title": seo_data["seo_title"],
            "meta_description": seo_data["meta_description"],
            "tags": seo_data["tags"],
            "keywords": seo_data["keywords"],
            "keyword_density": seo_data.get("keyword_density", 0.0)
        }

    except Exception as e:
        print(f"\n✗ SEO optimization failed: {str(e)}")
        # Provide fallback SEO data
        return {
            "seo_metadata": {},
            "seo_title": article_title[:60],
            "meta_description": article_content[:160],
            "tags": Config.DEFAULT_TAGS,
            "keywords": [],
            "keyword_density": 0.0,
            "errors": state.get("errors", []) + [f"SEO error: {str(e)}"]
        }


def parse_seo_output(seo_output: str) -> Dict[str, Any]:
    """
    Parse SEO optimization output

    Args:
        seo_output: Raw SEO output from LLM

    Returns:
        Dictionary with parsed SEO data
    """
    seo_data = {
        "seo_title": "",
        "meta_description": "",
        "keywords": [],
        "tags": [],
        "keyword_density": 0.0,
        "notes": ""
    }

    # Extract SEO title
    title_match = re.search(r'SEO_TITLE:\s*(.+?)(?:\n|$)', seo_output, re.IGNORECASE)
    if title_match:
        seo_data["seo_title"] = title_match.group(1).strip()

    # Extract meta description
    desc_match = re.search(r'META_DESCRIPTION:\s*(.+?)(?:\n\n|$)', seo_output, re.IGNORECASE | re.DOTALL)
    if desc_match:
        seo_data["meta_description"] = desc_match.group(1).strip()

    # Extract keywords
    keywords_section = re.search(
        r'PRIMARY_KEYWORDS?:\s*\n((?:[-*]\s*.+?\n)+)',
        seo_output,
        re.IGNORECASE
    )
    if keywords_section:
        keyword_lines = keywords_section.group(1)
        keywords = re.findall(r'[-*]\s*(.+)', keyword_lines)
        seo_data["keywords"] = [k.strip() for k in keywords]

    # Extract tags using TagExtractionTool
    tags_section = re.search(
        r'TAGS?:\s*\n((?:[-*]\s*.+?\n)+)',
        seo_output,
        re.IGNORECASE
    )
    if tags_section:
        tag_extractor = TagExtractionTool()
        tags_text = tags_section.group(1)
        import json
        tags_result = tag_extractor._run(tags_text)
        tags_data = json.loads(tags_result)
        seo_data["tags"] = tags_data.get("tags", [])

    # Extract keyword density
    density_match = re.search(r'KEYWORD_DENSITY:\s*([\d.]+)', seo_output, re.IGNORECASE)
    if density_match:
        seo_data["keyword_density"] = float(density_match.group(1))

    # Extract notes
    notes_match = re.search(r'SEO_NOTES:\s*\n(.+)', seo_output, re.IGNORECASE | re.DOTALL)
    if notes_match:
        seo_data["notes"] = notes_match.group(1).strip()

    return seo_data
