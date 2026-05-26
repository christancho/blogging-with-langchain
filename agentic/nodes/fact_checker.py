"""
Fact checker node - two-phase LLM pipeline for claim extraction and live verification
"""
import json
from datetime import datetime
from typing import Dict, Any, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from nodes.prompt_loader import PromptLoader
from tools import BraveSearchTool, URLFetcherTool


MAX_URLS_PER_CLAIM = 2
MAX_CLAIMS = 20  # Cap to control cost on very long articles


def fact_checker_node(state: BlogState) -> Dict[str, Any]:
    """
    Fact checker node: two-phase LLM pipeline that extracts all factual claims
    from the article and verifies each one against live web sources.

    Phase 1 - Claim extraction: LLM reads article, outputs structured claim list.
    Phase 2 - Claim verification: For each claim, Brave search + URL fetch, then
    LLM verdict (true / false / unverifiable) with source URL.

    On any false verdict: reject and return structured feedback to the writer.
    On all true/unverifiable: pass forward to formatter.

    Args:
        state: Current blog state

    Returns:
        Partial state update with fact_check_status, fact_verdicts, fact_check_feedback
    """
    print("\n" + "="*80)
    print("FACT CHECKER NODE")
    print("="*80)

    article_content = state.get("article_content", "")
    fact_revision_count = state.get("fact_revision_count", 0)
    fact_max_revisions = state.get("fact_max_revisions", 3)
    current_date = datetime.now().strftime("%B %d, %Y")

    print(f"Checking facts in article ({len(article_content.split())} words)")
    print(f"Attempt: {fact_revision_count + 1}/{fact_max_revisions + 1}")

    if not article_content:
        print("✗ No article content to fact-check")
        return {
            "fact_check_status": "passed",
            "fact_verdicts": [],
            "fact_check_feedback": "",
        }

    llm = Config.get_llm()
    search_tool = BraveSearchTool()
    url_fetcher = URLFetcherTool()

    # =========================================================================
    # PHASE 1: Extract factual claims
    # =========================================================================
    print("\n📋 Phase 1: Extracting factual claims...")

    extract_template = PromptLoader.load("fact_checker_extract")
    extract_prompt_text = extract_template.render(
        article_content=article_content,
        current_date=current_date
    )
    # Escape all remaining braces for ChatPromptTemplate (covers JSON examples in the prompt)
    extract_prompt_text = extract_prompt_text.replace("{", "{{").replace("}", "}}")

    extract_prompt = ChatPromptTemplate.from_messages([
        ("system", extract_prompt_text),
        ("human", "Extract all factual claims now.")
    ])
    extract_chain = extract_prompt | llm | StrOutputParser()

    try:
        raw_claims = extract_chain.invoke({})
        claims = _parse_json(raw_claims, fallback=[])
    except Exception as e:
        print(f"  ✗ Claim extraction failed: {e}")
        return {
            "fact_check_status": "passed",
            "fact_verdicts": [],
            "fact_check_feedback": "",
            "warnings": state.get("warnings", []) + [f"Fact checker extraction failed: {e}"]
        }

    if not claims:
        print("  ✓ No verifiable claims found — passing")
        return {
            "fact_check_status": "passed",
            "fact_verdicts": [],
            "fact_check_feedback": "",
        }

    # Cap claim count to control cost
    if len(claims) > MAX_CLAIMS:
        print(f"  ⚠ Capping claims from {len(claims)} to {MAX_CLAIMS}")
        claims = claims[:MAX_CLAIMS]

    print(f"  ✓ Extracted {len(claims)} claims")

    # =========================================================================
    # PHASE 2: Verify each claim against live sources
    # =========================================================================
    print("\n🔍 Phase 2: Verifying claims against live sources...")

    verify_template = PromptLoader.load("fact_checker_verify")
    verdicts = []

    for i, claim_item in enumerate(claims, 1):
        claim_text = claim_item.get("claim", "")
        context_text = claim_item.get("context", "")
        query = claim_item.get("suggested_query", claim_text)

        print(f"\n  [{i}/{len(claims)}] {claim_text[:80]}...")

        # Search for evidence
        search_content = _gather_search_content(query, search_tool, url_fetcher)

        if not search_content:
            verdicts.append({
                "claim": claim_text,
                "verdict": "unverifiable",
                "correct_information": None,
                "source_url": None,
                "confidence": "low"
            })
            print(f"    → unverifiable (no search results)")
            continue

        # Verify claim against fetched content
        verify_prompt_text = verify_template.render(
            claim=claim_text,
            context=context_text,
            search_content=search_content,
            current_date=current_date
        )
        # Escape all remaining braces for ChatPromptTemplate (covers JSON example in the prompt)
        verify_prompt_text = verify_prompt_text.replace("{", "{{").replace("}", "}}")

        verify_prompt = ChatPromptTemplate.from_messages([
            ("system", verify_prompt_text),
            ("human", "Verify this claim now.")
        ])
        verify_chain = verify_prompt | llm | StrOutputParser()

        try:
            raw_verdict = verify_chain.invoke({})
            verdict = _parse_json(raw_verdict, fallback={
                "claim": claim_text,
                "verdict": "unverifiable",
                "correct_information": None,
                "source_url": None,
                "confidence": "low"
            })
            verdicts.append(verdict)
            status_icon = "✓" if verdict.get("verdict") == "true" else ("✗" if verdict.get("verdict") == "false" else "~")
            print(f"    → {status_icon} {verdict.get('verdict')} ({verdict.get('confidence', '?')} confidence)")
        except Exception as e:
            print(f"    → ✗ Verification error: {e}")
            verdicts.append({
                "claim": claim_text,
                "verdict": "unverifiable",
                "correct_information": None,
                "source_url": None,
                "confidence": "low"
            })

    # =========================================================================
    # DECISION
    # =========================================================================
    false_verdicts = [v for v in verdicts if v.get("verdict") == "false"]

    print(f"\n📊 Results: {len(verdicts)} claims checked")
    print(f"   ✓ True: {len([v for v in verdicts if v.get('verdict') == 'true'])}")
    print(f"   ~ Unverifiable: {len([v for v in verdicts if v.get('verdict') == 'unverifiable'])}")
    print(f"   ✗ False: {len(false_verdicts)}")

    if not false_verdicts:
        print("\n✅ PASSED — all claims verified or unverifiable")
        return {
            "fact_check_status": "passed",
            "fact_verdicts": verdicts,
            "fact_check_feedback": "",
        }

    # Build structured feedback for the writer
    if fact_revision_count >= fact_max_revisions:
        print(f"\n⚠ FORCE PASSED — max fact revisions ({fact_max_revisions}) reached")
        feedback = _build_feedback(false_verdicts)
        return {
            "fact_check_status": "force_passed",
            "fact_verdicts": verdicts,
            "fact_check_feedback": feedback,
            "warnings": state.get("warnings", []) + [
                f"Force-passed fact check after {fact_max_revisions} revisions. "
                f"{len(false_verdicts)} false claim(s) remain."
            ]
        }

    feedback = _build_feedback(false_verdicts)
    print(f"\n❌ FAILED — {len(false_verdicts)} false claim(s) found, routing back to writer")
    print(feedback)

    return {
        "fact_check_status": "failed",
        "fact_verdicts": verdicts,
        "fact_check_feedback": feedback,
        "fact_revision_count": fact_revision_count + 1,
    }


def _gather_search_content(query: str, search_tool: BraveSearchTool, url_fetcher: URLFetcherTool) -> str:
    """Search for query and fetch top URL content. Returns combined text for LLM."""
    try:
        raw = search_tool._run(query)
        results = json.loads(raw).get("results", [])
    except Exception:
        return ""

    if not results:
        return ""

    parts = []

    # Include search result snippets
    for r in results[:5]:
        title = r.get("title", "")
        url = r.get("url", "")
        description = r.get("description", "")
        if title or description:
            parts.append(f"[Search result] {title}\nURL: {url}\n{description}")

    # Fetch full content from top URLs
    fetched = 0
    for r in results[:MAX_URLS_PER_CLAIM]:
        url = r.get("url", "")
        if not url:
            continue
        result = url_fetcher.fetch_url_content(url)
        content = result.get("content", "")
        if content:
            parts.append(f"[Full page content from {url}]\n{content[:3000]}")
            fetched += 1
        if fetched >= MAX_URLS_PER_CLAIM:
            break

    return "\n\n---\n\n".join(parts)


def _build_feedback(false_verdicts: List[Dict[str, Any]]) -> str:
    """Build structured correction list to pass to the writer."""
    lines = [
        "The following factual claims in your article were found to be incorrect. "
        "Please correct each one before resubmitting.\n"
    ]
    for i, v in enumerate(false_verdicts, 1):
        lines.append(f"{i}. INCORRECT CLAIM: {v.get('claim')}")
        if v.get("correct_information"):
            lines.append(f"   CORRECT INFORMATION: {v.get('correct_information')}")
        if v.get("source_url"):
            lines.append(f"   SOURCE: {v.get('source_url')}")
        lines.append("")
    return "\n".join(lines)


def _parse_json(text: str, fallback: Any) -> Any:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback
