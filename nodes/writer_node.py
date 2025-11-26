"""
Writer node for creating blog content
"""
from typing import Dict, Any
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from prompts import WRITER_PROMPT


def get_llm():
    """Get the configured LLM"""
    llm_config = Config.get_llm_config()

    if llm_config["provider"] == "anthropic":
        return ChatAnthropic(
            api_key=llm_config["api_key"],
            model=llm_config["model"],
            temperature=llm_config["temperature"],
        )
    else:  # openrouter
        return ChatOpenAI(
            api_key=llm_config["api_key"],
            model=llm_config["model"],
            base_url=llm_config["base_url"],
            temperature=llm_config["temperature"],
        )


def writer_node(state: BlogState) -> Dict[str, Any]:
    """
    Writer node: Generate comprehensive blog article

    Args:
        state: Current blog state

    Returns:
        Partial state update with article content
    """
    print("\n" + "="*80)
    print("WRITER NODE")
    print("="*80)

    topic = state["topic"]
    research_summary = state.get("research_summary", "")

    print(f"Topic: {topic}")
    print(f"Research summary length: {len(research_summary)} characters")

    # Initialize LLM
    llm = get_llm()

    # Create prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", WRITER_PROMPT),
        ("human", "Write the article now.")
    ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Generate article
    try:
        article_content = chain.invoke({
            "topic": topic,
            "tone": Config.BLOG_TONE,
            "research_summary": research_summary
        })

        # Extract inline links
        import re
        md_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', article_content)
        inline_links = [url for _, url in md_links]

        # Extract title (first H1)
        title_match = re.search(r'^#\s+(.+)$', article_content, re.MULTILINE)
        article_title = title_match.group(1).strip() if title_match else topic

        # Count words
        word_count = len(article_content.split())

        print(f"\n✓ Article generated")
        print(f"  - Title: {article_title}")
        print(f"  - Word count: {word_count}")
        print(f"  - Inline links: {len(inline_links)}")

        return {
            "article_content": article_content,
            "article_title": article_title,
            "inline_links": inline_links,
        }

    except Exception as e:
        print(f"\n✗ Writing failed: {str(e)}")
        return {
            "article_content": "",
            "article_title": topic,
            "inline_links": [],
            "errors": state.get("errors", []) + [f"Writing error: {str(e)}"]
        }
