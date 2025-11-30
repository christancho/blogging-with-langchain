"""
Editorial supervisor node - combines editing and quality review
"""
import json
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from nodes.prompt_loader import PromptLoader
from tools import ContentAnalysisTool


def editor_node(state: BlogState) -> Dict[str, Any]:
    """
    Editor node: Refine and validate article quality before publication

    Args:
        state: Current blog state

    Returns:
        Partial state update with edited content and quality assessment
    """
    print("\n" + "="*80)
    print("EDITORIAL SUPERVISOR NODE")
    print("="*80)

    formatted_content = state.get("formatted_content", "")
    instructions = state.get("instructions", "") or "No specific instructions provided."

    print(f"Reviewing and editing article for publication quality")
    print(f"Instructions: {instructions[:80]}..." if len(instructions) > 80 else f"Instructions: {instructions}")

    # Analyze content with ContentAnalysisTool
    content_analyzer = ContentAnalysisTool()
    analysis_result = content_analyzer._run(formatted_content)
    analysis = json.loads(analysis_result)

    print(f"\n📊 Content Analysis (Pre-Edit):")
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

    # Calculate initial pass/fail
    checks_passed = sum(quality_checks.values())
    total_checks = len(quality_checks)

    print(f"\n✓ Quality Checks (Pre-Edit): {checks_passed}/{total_checks} passed")
    for check, passed in quality_checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}: {passed}")

    # Use LLM for editorial refinement and quality review
    llm = Config.get_llm()

    editor_template = PromptLoader.load("editor")
    editor_prompt = editor_template.render(
        article_content=formatted_content,
        instructions=instructions
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", editor_prompt),
        ("human", "Review, edit, and refine this article for publication.")
    ])

    chain = prompt | llm | StrOutputParser()

    try:
        print(f"\n🔄 Performing editorial review and refinement...")

        # Get LLM editorial review (which should return the edited article)
        edited_content = chain.invoke({})

        # Verify we got back actual content
        word_count_edited = len(edited_content.split())

        if word_count_edited < 1000:
            # LLM probably returned a review instead of the article
            print("\n⚠ Warning: LLM returned review instead of article, using formatted content")
            final_content = formatted_content
        else:
            final_content = edited_content
            print(f"✓ Editorial review completed")

        # Analyze edited content
        analysis_result_edited = content_analyzer._run(final_content)
        analysis_edited = json.loads(analysis_result_edited)

        print(f"\n📊 Content Analysis (Post-Edit):")
        print(f"  - Word count: {analysis_edited['word_count']}")
        print(f"  - Links: {analysis_edited['links']['total_links']}")
        print(f"  - Quality score: {analysis_edited['quality_score']}")

        # Re-check quality after editing
        quality_checks_final = {
            "word_count": analysis_edited["word_count"] >= Config.WORD_COUNT_TARGET,
            "min_links": analysis_edited["links"]["total_links"] >= Config.MIN_INLINE_LINKS,
            "well_structured": analysis_edited["structure"]["well_structured"],
            "has_h1": analysis_edited["structure"]["h1_count"] == 1,
            "has_sections": analysis_edited["structure"]["h2_count"] >= Config.NUM_SECTIONS
        }

        checks_passed_final = sum(quality_checks_final.values())

        print(f"\n✓ Quality Checks (Post-Edit): {checks_passed_final}/{total_checks} passed")
        for check, passed in quality_checks_final.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}: {passed}")

        return {
            "quality_score": analysis_edited["quality_score"],
            "quality_checks": quality_checks_final,
            "editorial_notes": f"Quality improvement: {analysis['quality_score']} → {analysis_edited['quality_score']} | Checks passed: {checks_passed_final}/{total_checks}",
            "final_content": final_content
        }

    except Exception as e:
        print(f"\n✗ Editorial review failed: {str(e)}")
        # Return formatted content as fallback
        return {
            "quality_score": analysis["quality_score"],
            "quality_checks": quality_checks,
            "editorial_notes": f"Editorial error: {str(e)}",
            "final_content": formatted_content,
            "errors": state.get("errors", []) + [f"Editorial error: {str(e)}"]
        }
