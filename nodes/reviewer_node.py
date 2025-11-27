"""
Quality reviewer node
"""
import re
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from prompts import REVIEWER_PROMPT
from tools import ContentAnalysisTool


def reviewer_node(state: BlogState) -> Dict[str, Any]:
    """
    Reviewer node: Quality check and approve content

    Args:
        state: Current blog state

    Returns:
        Partial state update with quality assessment and final content
    """
    print("\n" + "="*80)
    print("REVIEWER NODE")
    print("="*80)

    formatted_content = state.get("formatted_content", "")

    print(f"Reviewing article quality")

    # Analyze content with ContentAnalysisTool
    content_analyzer = ContentAnalysisTool()
    import json
    analysis_result = content_analyzer._run(formatted_content)
    analysis = json.loads(analysis_result)

    print(f"\n📊 Content Analysis:")
    print(f"  - Word count: {analysis['word_count']}")
    print(f"  - Links: {analysis['links']['total_links']}")
    print(f"  - Quality score: {analysis['quality_score']}")

    # Perform quality checks
    quality_checks = {
        "word_count": analysis["word_count"] >= Config.WORD_COUNT_TARGET,
        "min_links": analysis["links"]["total_links"] >= Config.MIN_INLINE_LINKS,
        "well_structured": analysis["structure"]["well_structured"],
        "has_h1": analysis["structure"]["h1_count"] == 1,
        "has_sections": analysis["structure"]["h2_count"] >= Config.NUM_SECTIONS
    }

    # Calculate overall pass/fail
    checks_passed = sum(quality_checks.values())
    total_checks = len(quality_checks)

    print(f"\n✓ Quality Checks: {checks_passed}/{total_checks} passed")
    for check, passed in quality_checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}: {passed}")

    # Use LLM for final review and approval
    llm = Config.get_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", REVIEWER_PROMPT),
        ("human", "Review and return the final article.")
    ])

    chain = prompt | llm | StrOutputParser()

    try:
        # Get LLM review (which should return the full article)
        final_content = chain.invoke({
            "formatted_content": formatted_content
        })

        # If the LLM returned the full article, use it
        # Otherwise, use the formatted content
        word_count_final = len(final_content.split())

        if word_count_final < 1000:
            # LLM probably returned a review instead of the article
            print("\n⚠ Warning: LLM returned review instead of article, using formatted content")
            final_content = formatted_content
        else:
            print(f"\n✓ Review completed, final content: {word_count_final} words")

        return {
            "quality_score": analysis["quality_score"],
            "quality_checks": quality_checks,
            "review_notes": f"Quality score: {analysis['quality_score']} | Checks passed: {checks_passed}/{total_checks}",
            "final_content": final_content
        }

    except Exception as e:
        print(f"\n✗ Review failed: {str(e)}")
        # Return formatted content as fallback
        return {
            "quality_score": analysis["quality_score"],
            "quality_checks": quality_checks,
            "review_notes": f"Review error: {str(e)}",
            "final_content": formatted_content,
            "errors": state.get("errors", []) + [f"Review error: {str(e)}"]
        }
