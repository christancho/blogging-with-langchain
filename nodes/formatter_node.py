"""
HTML formatter node for Ghost CMS compatibility
"""
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from prompts import FORMATTER_PROMPT
from tools import HTMLFormatterTool


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

    # Create prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", FORMATTER_PROMPT),
        ("human", "Format the article now.")
    ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Format content
    try:
        formatted_content = chain.invoke({
            "article_content": article_content,
            "seo_metadata": str(seo_metadata)
        })

        # Use HTMLFormatterTool for additional cleanup
        formatter_tool = HTMLFormatterTool()
        formatted_content = formatter_tool._run(formatted_content)

        # Replace first H1 with SEO title if provided
        if seo_title:
            import re
            formatted_content = re.sub(
                r'^#\s+.+$',
                f'# {seo_title}',
                formatted_content,
                count=1,
                flags=re.MULTILINE
            )

        # Generate HTML version
        formatted_html = formatter_tool.markdown_to_html(formatted_content)

        print(f"\n✓ Formatting completed")
        print(f"  - Markdown length: {len(formatted_content)} chars")
        print(f"  - HTML length: {len(formatted_html)} chars")

        return {
            "formatted_content": formatted_content,
            "formatted_html": formatted_html
        }

    except Exception as e:
        print(f"\n✗ Formatting failed: {str(e)}")
        # Return original content as fallback
        return {
            "formatted_content": article_content,
            "formatted_html": article_content,
            "errors": state.get("errors", []) + [f"Formatting error: {str(e)}"]
        }
