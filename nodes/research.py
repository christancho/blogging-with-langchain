"""
Research node for gathering information
"""
import json
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from tools import BraveSearchTool, URLFetcherTool, LinkValidatorTool
from nodes.prompt_loader import PromptLoader


def research_node(state: BlogState) -> Dict[str, Any]:
    """
    Research node: Route to standard or deep research based on flag.

    Args:
        state: Current blog state

    Returns:
        Partial state update with research results
    """
    deep_research_enabled = state.get("deep_research_enabled", False)

    if deep_research_enabled:
        return _deep_research(state)
    else:
        return _standard_research(state)


def _standard_research(state: BlogState) -> Dict[str, Any]:
    """
    Standard research (current implementation).
    Performs shallow research with search metadata.

    Args:
        state: Current blog state

    Returns:
        Partial state update with research results
    """
    print("\n" + "="*80)
    print("RESEARCH NODE - STANDARD MODE")
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
    link_validator = LinkValidatorTool()

    # STEP 1: Extract and validate URLs from instructions
    fetched_content = []
    instruction_urls = []

    if instructions:
        instruction_urls = url_fetcher.extract_urls_from_text(instructions)
        if instruction_urls:
            print(f"\n📎 Found {len(instruction_urls)} URL(s) in instructions")

            # Validate URLs first
            valid_instruction_urls, _ = link_validator.validate_urls(instruction_urls, show_progress=True)

            # Fetch content only from valid URLs
            if valid_instruction_urls:
                print(f"\n📥 Fetching content from {len(valid_instruction_urls)} valid URLs...")
                for url in valid_instruction_urls:
                    result = url_fetcher.fetch_url_content(url)
                    if result.get("content"):
                        fetched_content.append(result)
                        print(f"   ✓ {url[:70]}... ({result['type']}, {len(result['content'])} chars)")
                    else:
                        print(f"   ✗ {url[:70]}... (fetch failed)")

    # STEP 2: Create research prompt with context about instructions
    research_template = PromptLoader.load("research")
    research_context = f"Custom Instructions: {instructions}" if instructions else "No specific instructions provided."
    current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "February 05, 2026"
    research_prompt = research_template.render(
        topic=topic,
        instructions_context=research_context,
        current_date=current_date
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
        all_sources = extract_sources_from_text(research_output)

        # Validate all extracted sources
        if all_sources:
            print(f"\n🔍 Found {len(all_sources)} source URLs from research")
            valid_sources, validation_results = link_validator.validate_urls(all_sources, show_progress=True)
        else:
            valid_sources = []
            validation_results = []

        # Escape curly braces in research output to prevent ChatPromptTemplate from
        # interpreting them as template variables when embedded in other prompts
        research_output_escaped = research_output.replace("{", "{{").replace("}", "}}")

        print(f"\n✓ Research completed")
        print(f"  - Priority URLs fetched: {len(fetched_content)}")
        print(f"  - Valid sources: {len(valid_sources)}/{len(all_sources)}")

        return {
            "research_summary": research_output_escaped,
            "research_sources": valid_sources,  # Only pass validated URLs
            "research_results": {
                "raw_output": research_output,
                "sources": valid_sources,
                "all_sources_found": all_sources,
                "invalid_sources": [r for r in validation_results if not r["is_valid"]],
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


def _deep_research(state: BlogState) -> Dict[str, Any]:
    """
    Deep research: Generate queries, fetch URLs, synthesize content.

    Workflow:
    1. Fetch priority URLs from instructions (if provided)
    2. Generate custom search queries (LLM)
    3. Execute searches via Brave API
    4. Fetch top 3 URLs per query
    5. Synthesize all content into structured data (LLM)
    6. Format for writer node

    Args:
        state: Current blog state

    Returns:
        Partial state update with deep research results
    """
    print("\n" + "="*80)
    print("🔬 DEEP RESEARCH MODE")
    print("="*80)

    topic = state["topic"]
    instructions = state.get("instructions", "")
    print(f"Topic: {topic}")
    if instructions:
        preview = instructions[:100] + "..." if len(instructions) > 100 else instructions
        print(f"Instructions: {preview}")

    # Initialize tools
    from tools import BraveSearchTool, URLFetcherTool, QueryGeneratorTool, ContentSynthesisTool, LinkValidatorTool
    search_tool = BraveSearchTool()
    url_fetcher = URLFetcherTool()
    query_generator = QueryGeneratorTool()
    synthesizer = ContentSynthesisTool()
    link_validator = LinkValidatorTool()

    all_fetched_urls = []
    all_queries = []

    # STEP 1: Validate and fetch priority URLs from instructions
    if instructions:
        instruction_urls = url_fetcher.extract_urls_from_text(instructions)
        if instruction_urls:
            print(f"\n📎 Found {len(instruction_urls)} priority URLs from instructions")

            # Validate URLs first
            valid_instruction_urls, _ = link_validator.validate_urls(instruction_urls, show_progress=True)

            # Fetch content only from valid URLs
            if valid_instruction_urls:
                print(f"\n📥 Fetching content from {len(valid_instruction_urls)} valid URLs...")
                for url in valid_instruction_urls:
                    result = url_fetcher.fetch_url_content(url)
                    if result.get("content"):
                        all_fetched_urls.append(result)
                        print(f"   ✓ {url[:70]}...")
                    else:
                        print(f"   ✗ Failed: {url[:70]}...")

    # STEP 2: Generate search queries
    print(f"\n🧠 Generating {Config.DEEP_RESEARCH_QUERIES} custom search queries...")
    try:
        queries = query_generator.generate_queries(
            topic,
            instructions,
            num_queries=Config.DEEP_RESEARCH_QUERIES
        )
        all_queries = queries
        print(f"Generated queries:")
        for q in queries:
            print(f"   - {q}")
    except Exception as e:
        print(f"⚠️  Query generation failed: {e}")
        # Fallback to hardcoded queries
        queries = [
            topic,
            f"{topic} best practices",
            f"{topic} use cases",
            f"{topic} latest developments"
        ]
        all_queries = queries

    # STEP 3: Execute searches, validate, and fetch URLs
    print(f"\n🔍 Searching and fetching top {Config.DEEP_RESEARCH_URLS_PER_QUERY} URLs per query...")

    for query_idx, query in enumerate(queries, 1):
        print(f"\n   Query {query_idx}/{len(queries)}: {query}")

        try:
            # Execute search
            search_result = search_tool._run(query)
            search_data = json.loads(search_result)

            # Get top N URLs
            candidate_urls = [
                r["url"] for r in search_data.get("results", [])
                [:Config.DEEP_RESEARCH_URLS_PER_QUERY * 2]  # Get extra candidates for validation filtering
            ]

            # Filter out already fetched URLs
            candidate_urls = [url for url in candidate_urls if url not in [f["url"] for f in all_fetched_urls]]

            if not candidate_urls:
                continue

            # Validate URLs
            print(f"   Validating {len(candidate_urls)} candidate URLs...")
            valid_urls, _ = link_validator.validate_urls(candidate_urls, show_progress=False)

            # Take top N valid URLs
            urls_to_fetch = valid_urls[:Config.DEEP_RESEARCH_URLS_PER_QUERY]

            if not urls_to_fetch:
                print(f"   ⚠️  No valid URLs found for this query")
                continue

            # Fetch each valid URL
            print(f"   Fetching {len(urls_to_fetch)} valid URLs...")
            for url in urls_to_fetch:
                # Check max limit
                if len(all_fetched_urls) >= Config.DEEP_RESEARCH_MAX_URLS_TOTAL:
                    print(f"   ⚠️  Reached max URL limit ({Config.DEEP_RESEARCH_MAX_URLS_TOTAL})")
                    break

                # Fetch content
                result = url_fetcher.fetch_url_content(url)
                if result.get("content"):
                    all_fetched_urls.append(result)
                    print(f"      ✓ {url[:60]}...")
                else:
                    print(f"      ✗ {url[:60]}...")

        except Exception as e:
            print(f"   ✗ Search/fetch failed: {e}")
            continue

    print(f"\n✓ Fetched {len(all_fetched_urls)} total URLs (all validated)")

    # STEP 4: Synthesize content
    print(f"\n🧬 Synthesizing research findings...")

    try:
        synthesis = synthesizer.synthesize_content(topic, all_fetched_urls)

        print(f"✓ Synthesis complete:")
        print(f"   - Key facts: {len(synthesis.get('key_facts', []))}")
        print(f"   - Quotes: {len(synthesis.get('quotes', []))}")
        print(f"   - Themes: {len(synthesis.get('themes', []))}")
    except Exception as e:
        print(f"⚠️  Synthesis failed: {e}")
        synthesis = {
            "summary": f"Research completed but synthesis failed: {e}",
            "key_facts": [],
            "quotes": [],
            "themes": [],
            "sources_by_priority": [f["url"] for f in all_fetched_urls]
        }

    # STEP 5: Format for writer
    research_summary = _format_deep_research_summary(synthesis, all_fetched_urls)

    # Extract source URLs
    sources = [f["url"] for f in all_fetched_urls]

    print(f"\n✅ Deep research completed successfully!")
    print("="*80)

    # Escape curly braces for prompt template compatibility
    research_summary_escaped = research_summary.replace("{", "{{").replace("}", "}}")

    return {
        "research_summary": research_summary_escaped,
        "research_sources": sources,
        "deep_research_enabled": True,
        "research_queries": all_queries,
        "research_fetched_urls": all_fetched_urls,
        "research_key_facts": synthesis.get("key_facts", []),
        "research_quotes": synthesis.get("quotes", []),
        "research_themes": synthesis.get("themes", []),
        "research_structured_data": synthesis,
        "research_results": {
            "mode": "deep",
            "queries_generated": len(all_queries),
            "urls_fetched": len(all_fetched_urls),
            "facts_extracted": len(synthesis.get("key_facts", [])),
            "quotes_found": len(synthesis.get("quotes", []))
        }
    }


def _format_deep_research_summary(synthesis: Dict[str, Any], fetched_urls: List[Dict]) -> str:
    """
    Format structured synthesis into text summary for writer prompt.

    Args:
        synthesis: Structured synthesis data
        fetched_urls: List of fetched URL data

    Returns:
        Formatted research summary string
    """
    parts = []

    parts.append("=== DEEP RESEARCH SUMMARY ===\n")
    parts.append(synthesis.get("summary", ""))

    parts.append("\n\n=== KEY FINDINGS (with sources) ===\n")
    for fact in synthesis.get("key_facts", [])[:15]:
        parts.append(f"\n• {fact['fact']}")
        parts.append(f"  [Source: {fact['source']}]")
        parts.append(f"  [Confidence: {fact.get('confidence', 'medium')}]")

    parts.append("\n\n=== NOTABLE QUOTES ===\n")
    for quote in synthesis.get("quotes", [])[:8]:
        parts.append(f'\n"{quote["quote"]}"')
        parts.append(f"  — {quote.get('author', 'Unknown')}")
        parts.append(f"  [Source: {quote['source']}]")

    parts.append("\n\n=== MAIN THEMES ===\n")
    for theme in synthesis.get("themes", []):
        parts.append(f"• {theme}\n")

    parts.append("\n\n=== AUTHORITATIVE SOURCES (ranked by priority) ===\n")
    for idx, url in enumerate(synthesis.get("sources_by_priority", [])[:15], 1):
        parts.append(f"{idx}. {url}\n")

    return "".join(parts)
