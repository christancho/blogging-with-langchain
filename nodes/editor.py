"""
Editorial supervisor node - LLM-based quality review with mechanical awareness
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
    Editor node: LLM-based quality approval gate with mechanical awareness

    Evaluates both editorial quality (cohesiveness, flow) and mechanical
    requirements (word count, links, structure). Routes to approval, rejection,
    or forced publish based on LLM assessment and revision count.

    Args:
        state: Current blog state

    Returns:
        Partial state update with approval decision and feedback
    """
    print("\n" + "="*80)
    print("EDITOR NODE - LLM-BASED APPROVAL GATE")
    print("="*80)

    # Read formatted article content (formatter runs before editor now)
    article_content = state.get("formatted_content", "") or state.get("article_content", "")
    instructions = state.get("instructions", "") or "No specific instructions provided."
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)
    word_count_target = state.get("word_count_target", Config.WORD_COUNT_TARGET)

    print(f"Reviewing article for publication quality")
    print(f"Revision: {revision_count + 1}/{max_revisions + 1}")

    # Analyze content with ContentAnalysisTool to get metrics
    content_analyzer = ContentAnalysisTool()
    analysis_result = content_analyzer._run(article_content)
    analysis = json.loads(analysis_result)

    print(f"\n📊 Content Analysis:")
    print(f"  - Word count: {analysis['word_count']}")
    print(f"  - Links: {analysis['links']['total_links']}")
    print(f"  - Quality score: {analysis['quality_score']}")

    # Calculate minimum word count (5% tolerance)
    min_word_count = int(word_count_target * 0.95)

    # Escape article content to prevent Jinja2 from interpreting curly braces as variables
    article_content_escaped = article_content.replace("{", "{{").replace("}", "}}")

    # Prepare prompt variables
    editor_template = PromptLoader.load("editor")
    editor_prompt_text = editor_template.render(
        article_content=article_content_escaped,
        instructions=instructions,
        current_word_count=analysis["word_count"],
        word_count_target=word_count_target,
        min_word_count=min_word_count,
        current_links=analysis["links"]["total_links"],
        min_links=Config.MIN_INLINE_LINKS,
        h1_count=analysis["structure"]["h1_count"],
        h2_count=analysis["structure"]["h2_count"],
        min_sections=Config.NUM_SECTIONS,
        quality_score=analysis["quality_score"]
    )

    # Create LLM chain
    prompt = ChatPromptTemplate.from_messages([
        ("system", editor_prompt_text),
        ("human", "Please provide your editorial assessment now in JSON format.")
    ])

    try:
        llm = Config.get_llm()
        chain = prompt | llm | StrOutputParser()

        print(f"\n🤖 Requesting LLM editorial review...")
        llm_response = chain.invoke({})

        # Parse JSON from response (handle markdown code blocks)
        json_match = llm_response
        if "```json" in llm_response:
            json_match = llm_response.split("```json")[1].split("```")[0].strip()
        elif "```" in llm_response:
            json_match = llm_response.split("```")[1].split("```")[0].strip()

        editorial_assessment = json.loads(json_match)

        # Extract fields
        cohesiveness_score = editorial_assessment.get("cohesiveness_score", 0)
        passes_review = editorial_assessment.get("passes_review", False)
        strengths = editorial_assessment.get("strengths", [])
        issues = editorial_assessment.get("issues", [])
        feedback = editorial_assessment.get("feedback", "No feedback provided.")

        print(f"\n📋 Editorial Assessment:")
        print(f"  - Cohesiveness score: {cohesiveness_score}/10")
        print(f"  - Passes review: {passes_review}")
        if strengths:
            print(f"  - Strengths ({len(strengths)}):")
            for strength in strengths:
                print(f"    • {strength}")
        if issues:
            print(f"  - Issues ({len(issues)}):")
            for issue in issues:
                print(f"    • {issue}")

    except Exception as e:
        # LLM evaluation failed - fall back to mechanical checks only
        print(f"\n⚠️  LLM evaluation failed: {str(e)}")
        print(f"Falling back to mechanical checks only")

        # Perform basic mechanical checks
        mechanical_checks = {
            "word_count": analysis["word_count"] >= min_word_count,
            "min_links": analysis["links"]["total_links"] >= Config.MIN_INLINE_LINKS,
            "has_h1": analysis["structure"]["h1_count"] == 1,
            "has_sections": analysis["structure"]["h2_count"] >= Config.NUM_SECTIONS
        }

        passes_review = all(mechanical_checks.values())
        cohesiveness_score = 7 if passes_review else 5
        strengths = ["Mechanical checks passed"] if passes_review else []
        issues = [f"{check} failed" for check, passed in mechanical_checks.items() if not passed]
        feedback = f"LLM evaluation unavailable. Mechanical checks: {', '.join(issues) if issues else 'all passed'}"

    # Route based on LLM assessment
    if passes_review:
        # APPROVED - all checks passed
        print(f"\n✅ APPROVED - Article meets editorial and mechanical standards")
        return {
            "approval_status": "approved",
            "approval_feedback": "",
            "quality_score": cohesiveness_score / 10,  # Normalize to 0-1
            "quality_checks": {
                "cohesiveness_score": cohesiveness_score,
                "passes_llm_review": passes_review,
                "editorial_strengths": strengths,
                "editorial_issues": issues
            },
            "review_notes": f"Approved on revision {revision_count + 1}. Cohesiveness score: {cohesiveness_score}/10. Strengths: {'; '.join(strengths[:2])}",
            "final_content": article_content,
            # Preserve SEO metadata for publisher
            "excerpt": state.get("excerpt", ""),
            "meta_description": state.get("meta_description", ""),
            "tags": state.get("tags", []),
            "keywords": state.get("keywords", []),
            "seo_title": state.get("seo_title", "")
        }
    else:
        # REJECTED - LLM or mechanical checks failed
        if revision_count >= max_revisions:
            # Max revisions exceeded - force publish with note
            print(f"\n⚠️  MAX REVISIONS EXCEEDED ({max_revisions}) - FORCING PUBLICATION WITH NOTE")
            forced_note = f"""**Editor's Note (Publication Override):**
This article was published after exceeding the maximum revision limit ({max_revisions} revisions).
The editorial review identified the following issues:

**Cohesiveness Score:** {cohesiveness_score}/10

**Issues Identified:**
{chr(10).join('- ' + issue for issue in issues)}

**Editorial Feedback:**
{feedback}

Please review and consider further editing in a follow-up post.

---

"""
            return {
                "approval_status": "force_publish",
                "approval_feedback": feedback,
                "quality_score": cohesiveness_score / 10,
                "quality_checks": {
                    "cohesiveness_score": cohesiveness_score,
                    "passes_llm_review": passes_review,
                    "editorial_strengths": strengths,
                    "editorial_issues": issues
                },
                "review_notes": f"Forced publish after {revision_count} revisions (max: {max_revisions}). Score: {cohesiveness_score}/10",
                "final_content": article_content,
                "forced_publish_note": forced_note,
                "warnings": state.get("warnings", []) + [f"Article published with editorial issues. Score: {cohesiveness_score}/10"],
                # Preserve SEO metadata for publisher
                "excerpt": state.get("excerpt", ""),
                "meta_description": state.get("meta_description", ""),
                "tags": state.get("tags", []),
                "keywords": state.get("keywords", []),
                "seo_title": state.get("seo_title", "")
            }
        else:
            # Send back for revision
            print(f"\n❌ REJECTED - Requesting revisions (attempt {revision_count + 1}/{max_revisions})")
            print(f"\nEditorial Feedback:")
            print(f"{feedback}")
            if issues:
                print(f"\nIssues to address:")
                for issue in issues:
                    print(f"  - {issue}")

            return {
                "approval_status": "rejected",
                "approval_feedback": feedback,
                "quality_score": cohesiveness_score / 10,
                "quality_checks": {
                    "cohesiveness_score": cohesiveness_score,
                    "passes_llm_review": passes_review,
                    "editorial_strengths": strengths,
                    "editorial_issues": issues
                },
                "review_notes": f"Rejected on revision {revision_count + 1}. Score: {cohesiveness_score}/10. Issues: {len(issues)}",
                "revision_count": revision_count + 1,
                # Preserve SEO metadata for next revision cycle
                "excerpt": state.get("excerpt", ""),
                "meta_description": state.get("meta_description", ""),
                "tags": state.get("tags", []),
                "keywords": state.get("keywords", []),
                "seo_title": state.get("seo_title", "")
            }
