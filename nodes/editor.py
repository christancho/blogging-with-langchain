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
    Editor node: Quality approval gate with rejection and revision loop

    Args:
        state: Current blog state

    Returns:
        Partial state update with approval decision and feedback
    """
    print("\n" + "="*80)
    print("EDITOR NODE - APPROVAL GATE")
    print("="*80)

    # Read article content from writer (before formatting)
    article_content = state.get("article_content", "")
    instructions = state.get("instructions", "") or "No specific instructions provided."
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)

    print(f"Reviewing article for publication quality")
    print(f"Revision: {revision_count + 1}/{max_revisions + 1}")

    # Analyze content with ContentAnalysisTool
    content_analyzer = ContentAnalysisTool()
    analysis_result = content_analyzer._run(article_content)
    analysis = json.loads(analysis_result)

    print(f"\n📊 Content Analysis:")
    print(f"  - Word count: {analysis['word_count']}")
    print(f"  - Links: {analysis['links']['total_links']}")
    print(f"  - Quality score: {analysis['quality_score']}")

    # Perform quality checks - REJECT ON ANY FAILURE
    quality_checks = {
        "word_count": analysis["word_count"] >= Config.WORD_COUNT_TARGET,
        "min_links": analysis["links"]["total_links"] >= Config.MIN_INLINE_LINKS,
        "well_structured": analysis["structure"]["well_structured"],
        "has_h1": analysis["structure"]["h1_count"] == 1,
        "has_sections": analysis["structure"]["h2_count"] >= Config.NUM_SECTIONS
    }

    checks_passed = sum(quality_checks.values())
    total_checks = len(quality_checks)

    print(f"\n✓ Quality Checks: {checks_passed}/{total_checks} passed")
    for check, passed in quality_checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}: {passed}")

    # Build specific feedback for failed checks
    failed_checks = [check for check, passed in quality_checks.items() if not passed]

    if not failed_checks:
        # All checks passed - APPROVE
        print(f"\n✅ APPROVED - All quality checks passed")
        return {
            "approval_status": "approved",
            "approval_feedback": "",
            "quality_score": analysis["quality_score"],
            "quality_checks": quality_checks,
            "review_notes": f"Approved on revision {revision_count + 1}. All checks passed.",
            "final_content": article_content
        }
    else:
        # Checks failed - build specific feedback
        feedback_parts = []

        for check in failed_checks:
            if check == "word_count":
                current = analysis["word_count"]
                target = Config.WORD_COUNT_TARGET
                feedback_parts.append(
                    f"Word count is {current}, but target is {target}. Please expand the article with more detailed content."
                )
            elif check == "min_links":
                current = analysis["links"]["total_links"]
                target = Config.MIN_INLINE_LINKS
                feedback_parts.append(
                    f"Only {current} inline links found, but {target} are required. Add more citations and references to support claims."
                )
            elif check == "well_structured":
                feedback_parts.append(
                    "Article structure is unclear. Ensure proper heading hierarchy, logical flow between sections, and clear topic development."
                )
            elif check == "has_h1":
                h1_count = analysis["structure"]["h1_count"]
                feedback_parts.append(
                    f"Article has {h1_count} H1 headings, but should have exactly 1. Add or remove H1 headings as needed."
                )
            elif check == "has_sections":
                current = analysis["structure"]["h2_count"]
                target = Config.NUM_SECTIONS
                feedback_parts.append(
                    f"Article has {current} sections (H2), but {target} are required. Add more major sections to improve article depth."
                )

        approval_feedback = "\n".join(feedback_parts)

        if revision_count >= max_revisions:
            # Max revisions exceeded - force publish with note
            print(f"\n⚠️  MAX REVISIONS EXCEEDED ({max_revisions}) - FORCING PUBLICATION WITH NOTE")
            forced_note = f"""**Editor's Note (Publication Override):**
This article was published after exceeding the maximum revision limit ({max_revisions} revisions).
The following quality issues remain unresolved:
- {chr(10).join('- ' + part for part in feedback_parts)}

Please review and consider further editing in a follow-up post.

---

"""
            return {
                "approval_status": "force_publish",
                "approval_feedback": approval_feedback,
                "quality_score": analysis["quality_score"],
                "quality_checks": quality_checks,
                "review_notes": f"Forced publish after {revision_count} revisions (max: {max_revisions}). Issues remain: {', '.join(failed_checks)}",
                "final_content": article_content,
                "forced_publish_note": forced_note,
                "warnings": state.get("warnings", []) + [f"Article published with unresolved quality issues: {', '.join(failed_checks)}"]
            }
        else:
            # Send back for revision
            print(f"\n❌ REJECTED - Requesting revisions (attempt {revision_count + 1}/{max_revisions})")
            print(f"Feedback:\n{approval_feedback}")
            return {
                "approval_status": "rejected",
                "approval_feedback": approval_feedback,
                "quality_score": analysis["quality_score"],
                "quality_checks": quality_checks,
                "review_notes": f"Rejected on revision {revision_count + 1}. Issues: {', '.join(failed_checks)}",
                "revision_count": revision_count + 1
            }
