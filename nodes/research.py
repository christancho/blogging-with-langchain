"""
Research node for gathering information
"""
import json
from datetime import datetime
from typing import Dict, Any, List
from state import BlogState
from config import Config


def research_node(state: BlogState) -> Dict[str, Any]:
    """
    Research node: Fetch and synthesize live web content for the topic.

    Workflow:
    1. Fetch priority URLs from instructions (if provided)
    2. Generate custom search queries (LLM)
    3. Execute searches via Brave API
    4. Fetch top N URLs per query (validated)
    5. Synthesize all content into structured key facts with sources
    6. Format for writer node

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

            valid_instruction_urls, _ = link_validator.validate_urls(instruction_urls, show_progress=True)

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
            search_result = search_tool._run(query)
            search_data = json.loads(search_result)

            candidate_urls = [
                r["url"] for r in search_data.get("results", [])
                [:Config.DEEP_RESEARCH_URLS_PER_QUERY * 2]
            ]

            candidate_urls = [url for url in candidate_urls if url not in [f["url"] for f in all_fetched_urls]]

            if not candidate_urls:
                continue

            print(f"   Validating {len(candidate_urls)} candidate URLs...")
            valid_urls, _ = link_validator.validate_urls(candidate_urls, show_progress=False)

            urls_to_fetch = valid_urls[:Config.DEEP_RESEARCH_URLS_PER_QUERY]

            if not urls_to_fetch:
                print(f"   ⚠️  No valid URLs found for this query")
                continue

            print(f"   Fetching {len(urls_to_fetch)} valid URLs...")
            for url in urls_to_fetch:
                if len(all_fetched_urls) >= Config.DEEP_RESEARCH_MAX_URLS_TOTAL:
                    print(f"   ⚠️  Reached max URL limit ({Config.DEEP_RESEARCH_MAX_URLS_TOTAL})")
                    break

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
    research_summary = _format_research_summary(synthesis, all_fetched_urls)

    # STEP 6: Generate headline candidates from synthesis
    headline_candidates = _extract_headlines(research_summary)
    if not headline_candidates:
        headline_candidates = _extract_headlines(synthesis.get("summary", ""))
    if headline_candidates:
        print(f"\n📰 Generated {len(headline_candidates)} headline candidates")

    sources = [f["url"] for f in all_fetched_urls]

    print(f"\n✅ Research completed successfully!")
    print("="*80)

    research_summary_escaped = research_summary.replace("{", "{{").replace("}", "}}")

    return {
        "research_summary": research_summary_escaped,
        "research_sources": sources,
        "headline_candidates": headline_candidates,
        "research_queries": all_queries,
        "research_fetched_urls": all_fetched_urls,
        "research_key_facts": synthesis.get("key_facts", []),
        "research_quotes": synthesis.get("quotes", []),
        "research_themes": synthesis.get("themes", []),
        "research_structured_data": synthesis,
        "research_results": {
            "queries_generated": len(all_queries),
            "urls_fetched": len(all_fetched_urls),
            "facts_extracted": len(synthesis.get("key_facts", [])),
            "quotes_found": len(synthesis.get("quotes", []))
        }
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


def _extract_headlines(research_text: str) -> List[str]:
    """
    Extract headline candidates from research output.

    Looks for a numbered list under a 'Headline Candidates' section.

    Args:
        research_text: Raw research output from LLM

    Returns:
        List of headline strings
    """
    import re

    headlines = []

    # Find the headline candidates section
    headline_section_match = re.search(
        r'(?:Headline Candidates|headline candidates)[:\s]*\n((?:\s*\d+[\.\)]\s*.+\n?)+)',
        research_text,
        re.IGNORECASE
    )

    if headline_section_match:
        section_text = headline_section_match.group(1)
        # Extract numbered items
        items = re.findall(r'\d+[\.\)]\s*(.+)', section_text)
        headlines = [item.strip().strip('"').strip("'") for item in items if item.strip()]

    return headlines[:7]  # Cap at 7




def _format_research_summary(synthesis: Dict[str, Any], fetched_urls: List[Dict]) -> str:
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
