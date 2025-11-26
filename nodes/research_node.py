"""
Research node for gathering information
"""
import json
from typing import Dict, Any
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate

from state import BlogState
from config import Config
from tools import BraveSearchTool
from prompts import RESEARCH_PROMPT


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
    llm = get_llm()
    search_tool = BraveSearchTool()

    # Create agent
    prompt = ChatPromptTemplate.from_messages([
        ("system", RESEARCH_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_tool_calling_agent(llm, [search_tool], prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=[search_tool],
        verbose=True,
        max_iterations=10,
        handle_parsing_errors=True
    )

    # Execute research
    try:
        result = agent_executor.invoke({
            "input": f"Research this topic: {topic}",
            "topic": topic
        })

        research_output = result.get("output", "")

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
