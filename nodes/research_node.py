"""
Research node for gathering information
"""
import json
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from tools import BraveSearchTool
from prompts import RESEARCH_PROMPT


def research_node(state: BlogState) -> Dict[str, Any]:
    """
    Research node: Gather information on the topic using web search

    Args:
        state: Current blog state

    Returns:
        Partial state update with research results
    """
    print("\n" + "="*80)
    print("RESEARCH NODE")
    print("="*80)

    topic = state["topic"]
    print(f"Topic: {topic}")

    # Initialize LLM and tools
    llm = Config.get_llm()
    search_tool = BraveSearchTool()

    # Create research prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", RESEARCH_PROMPT),
        ("human", "Research this topic: {topic}")
    ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Execute research
    try:
        # Get LLM to plan research queries
        research_plan = chain.invoke({"topic": topic})

        # Execute searches based on the research plan
        # For simplicity, we'll perform a few targeted searches
        search_queries = [
            topic,
            f"{topic} latest developments",
            f"{topic} best practices",
            f"{topic} use cases"
        ]

        search_results = []
        for query in search_queries[:5]:  # Limit to 5 searches
            try:
                result = search_tool._run(query)
                search_results.append(result)
            except Exception as e:
                print(f"Search failed for '{query}': {e}")

        # Combine search results with LLM research plan
        research_output = research_plan + "\n\n" + "\n".join(search_results)

        # Extract sources from the output
        sources = extract_sources_from_text(research_output)

        print(f"\n✓ Research completed")
        print(f"  - Found {len(sources)} sources")

        return {
            "research_summary": research_output,
            "research_sources": sources,
            "research_results": {
                "raw_output": research_output,
                "sources": sources,
                "topic": topic
            }
        }

    except Exception as e:
        print(f"\n✗ Research failed: {str(e)}")
        return {
            "research_summary": f"Research encountered an error: {str(e)}",
            "research_sources": [],
            "research_results": {"error": str(e)},
            "errors": state.get("errors", []) + [f"Research error: {str(e)}"]
        }


def extract_sources_from_text(text: str) -> list:
    """
    Extract URLs from research output

    Args:
        text: Research output text

    Returns:
        List of URLs
    """
    import re

    # Find all URLs in the text
    url_pattern = r'https?://[^\s\)\]"]+'
    urls = re.findall(url_pattern, text)

    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls
