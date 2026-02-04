"""
Research node for gathering information
"""
import json
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from tools import BraveSearchTool, URLFetcherTool
from nodes.prompt_loader import PromptLoader


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
    instructions = state.get("instructions", "")
    print(f"Topic: {topic}")
    if instructions:
        print(f"Instructions: {instructions[:100]}..." if len(instructions) > 100 else f"Instructions: {instructions}")

    # Initialize LLM and tools
    llm = Config.get_llm()
    search_tool = BraveSearchTool()
    url_fetcher = URLFetcherTool()

    # STEP 1: Extract and fetch content from URLs in instructions
    fetched_content = []
    instruction_urls = []

    if instructions:
        instruction_urls = url_fetcher.extract_urls_from_text(instructions)
        if instruction_urls:
            print(f"\n📎 Found {len(instruction_urls)} URL(s) in instructions:")
            for url in instruction_urls:
                print(f"   - {url}")
                result = url_fetcher.fetch_url_content(url)
                if result.get("content"):
                    fetched_content.append(result)
                    print(f"     ✓ Fetched ({result['type']}): {len(result['content'])} chars")
                else:
                    print(f"     ✗ Failed to fetch: {result.get('error', 'Unknown error')}")

    # STEP 2: Create research prompt with context about instructions
    research_template = PromptLoader.load("research")
    research_context = f"Custom Instructions: {instructions}" if instructions else "No specific instructions provided."
    research_prompt = research_template.render(
        topic=topic,
        instructions_context=research_context
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", research_prompt),
        ("human", "Research this topic: {topic}")
    ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Execute research
    try:
        # Get LLM to plan research queries
        research_plan = chain.invoke({"topic": topic})

        # STEP 3: Execute supplementary web searches
        search_queries = [
            topic,
            f"{topic} latest developments",
            f"{topic} best practices",
            f"{topic} use cases"
        ]

        search_results = []
        print(f"\n🔍 Performing {len(search_queries[:5])} supplementary web searches...")
        for query in search_queries[:5]:  # Limit to 5 searches
            try:
                result = search_tool._run(query)
                search_results.append(result)
            except Exception as e:
                print(f"  ✗ Search failed for '{query}': {e}")

        # STEP 4: Combine all research sources
        # Priority: 1) Fetched URL content, 2) Research plan, 3) Web searches
        research_output_parts = []

        if fetched_content:
            research_output_parts.append("=== PRIORITY SOURCES FROM INSTRUCTIONS ===\n")
            for idx, content_data in enumerate(fetched_content, 1):
                research_output_parts.append(f"\n--- Source {idx}: {content_data['url']} ---\n")
                research_output_parts.append(content_data['content'])
                research_output_parts.append("\n")

        research_output_parts.append("\n=== RESEARCH PLAN ===\n")
        research_output_parts.append(research_plan)

        if search_results:
            research_output_parts.append("\n\n=== SUPPLEMENTARY WEB SEARCH RESULTS ===\n")
            research_output_parts.append("\n".join(search_results))

        research_output = "\n".join(research_output_parts)

        # Extract sources from the output
        sources = extract_sources_from_text(research_output)

        # Escape curly braces in research output to prevent ChatPromptTemplate from
        # interpreting them as template variables when embedded in other prompts
        research_output_escaped = research_output.replace("{", "{{").replace("}", "}}")

        print(f"\n✓ Research completed")
        print(f"  - Priority URLs fetched: {len(fetched_content)}")
        print(f"  - Total sources found: {len(sources)}")

        return {
            "research_summary": research_output_escaped,
            "research_sources": sources,
            "research_results": {
                "raw_output": research_output,
                "sources": sources,
                "fetched_urls": instruction_urls,
                "fetched_content_count": len(fetched_content),
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
