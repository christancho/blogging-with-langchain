"""
Writer node for creating blog content
"""
import json
from datetime import datetime
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agentic.state import BlogState
from agentic.config import Config
from agentic.nodes.prompt_loader import PromptLoader
from agentic.tools import ContentAnalysisTool


def writer_node(state: BlogState) -> Dict[str, Any]:
    """
    Writer node: Generate comprehensive blog article or revise based on editor feedback

    Args:
        state: Current blog state

    Returns:
        Partial state update with article content
    """
    print("\n" + "="*80)
    print("WRITER NODE")
    print("="*80)

    topic = state["topic"]
    instructions = state.get("instructions", "") or "No specific instructions provided."
    research_summary = state.get("research_summary", "")
    revision_count = state.get("revision_count", 0)
    approval_feedback = state.get("approval_feedback", "")
    fact_check_feedback = state.get("fact_check_feedback", "")
    fact_revision_count = state.get("fact_revision_count", 0)

    # Initialize LLM
    llm = Config.get_llm()

    # Combine feedback sources — fact-check corrections take priority
    combined_feedback = ""
    if fact_check_feedback and fact_revision_count > 0:
        combined_feedback = fact_check_feedback
        if approval_feedback:
            combined_feedback += f"\n\nAdditional editorial feedback:\n{approval_feedback}"
    else:
        combined_feedback = approval_feedback

    # Check if this is a revision
    is_revision = (revision_count > 0 or fact_revision_count > 0) and combined_feedback
    approval_feedback = combined_feedback

    if is_revision:
        # REVISION MODE - Use feedback from editor
        attempt = fact_revision_count if fact_revision_count > 0 else revision_count
        print(f"REVISION MODE - Attempt {attempt}")
        print(f"Topic: {topic}")
        print(f"Revising based on editor feedback...")

        # Get the article content to revise (the rejected article_content)
        article_content_to_revise = state.get("article_content", "")

        if not article_content_to_revise:
            print(f"\n✗ No content to revise")
            return {
                "article_content": "",
                "article_title": topic,
                "inline_links": [],
                "errors": state.get("errors", []) + ["No article content available for revision"]
            }

        # Escape curly braces in article content and feedback to prevent ChatPromptTemplate from
        # interpreting them as template variables
        article_content_escaped = article_content_to_revise.replace("{", "{{").replace("}", "}}")
        feedback_escaped = approval_feedback.replace("{", "{{").replace("}", "}}")

        # Calculate word count tolerance (minimum 5% below target, no upper limit)
        word_count_target = state.get("word_count_target", Config.WORD_COUNT_TARGET)
        min_word_count = int(word_count_target * 0.95)
        max_word_count = word_count_target * 2  # Soft limit for guidance (no strict upper limit)

        # Use revision prompt
        revision_template = PromptLoader.load("revision")
        current_date = datetime.now().strftime("%B %d, %Y")
        research_key_facts = state.get("research_key_facts", [])
        revision_prompt = revision_template.render(
            topic=topic,
            article_content=article_content_escaped,
            editor_feedback=feedback_escaped,
            word_count_target=word_count_target,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            current_date=current_date,
            research_key_facts=research_key_facts,
            is_fact_revision=(
                fact_revision_count > 0
                and fact_check_feedback
                and state.get("fact_check_status") == "failed"
            ),
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", revision_prompt),
            ("human", "Please revise the article now.")
        ])

        print(f"Editor feedback to address:")
        print(f"{approval_feedback}")

    else:
        # INITIAL WRITE MODE
        print(f"INITIAL WRITE MODE")
        print(f"Topic: {topic}")
        print(f"Instructions: {instructions[:80]}..." if len(instructions) > 80 else f"Instructions: {instructions}")
        print(f"Research summary length: {len(research_summary)} characters")

        # Calculate word count tolerance (minimum 5% below target, no upper limit)
        word_count_target = state.get("word_count_target", Config.WORD_COUNT_TARGET)
        min_word_count = int(word_count_target * 0.95)
        max_word_count = word_count_target * 2  # Soft limit for guidance (no strict upper limit)

        # Use standard writer prompt
        writer_template = PromptLoader.load("writer")
        current_date = datetime.now().strftime("%B %d, %Y")
        headline_candidates = state.get("headline_candidates", [])
        audience_analysis = state.get("audience_analysis", "")
        research_key_facts = state.get("research_key_facts", [])
        writer_prompt = writer_template.render(
            topic=topic,
            tone=state.get("tone", Config.BLOG_TONE),
            instructions=instructions,
            research_summary=research_summary,
            audience_analysis=audience_analysis,
            headline_candidates=headline_candidates,
            word_count_target=word_count_target,
            min_word_count=min_word_count,
            max_word_count=max_word_count,
            current_date=current_date,
            research_key_facts=research_key_facts,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", writer_prompt),
            ("human", "Write the article now.")
        ])

    # Create chain
    chain = prompt | llm | StrOutputParser()

    # Generate or revise article
    try:
        revised_content = chain.invoke({})

        # Self-check mechanical requirements using the same method the editor uses
        # (word count excludes code blocks, matching ContentAnalysisTool._count_words)
        analyzer = ContentAnalysisTool()
        MAX_SELF_CHECK_RETRIES = 1
        for check_attempt in range(MAX_SELF_CHECK_RETRIES + 1):
            check = json.loads(analyzer._run(revised_content))
            check_words = check["word_count"]
            check_links = check["links"]["total_links"]
            check_h1 = check["structure"]["h1_count"]
            check_h2 = check["structure"]["h2_count"]

            issues = []
            if check_words < min_word_count:
                gap = min_word_count - check_words
                issues.append(
                    f"Word count is {check_words} (minimum is {min_word_count}). "
                    f"Add ~{gap} more words by deepening examples or expanding key sections."
                )
            if check_links < Config.MIN_INLINE_LINKS:
                issues.append(
                    f"Only {check_links} inline links (minimum is {Config.MIN_INLINE_LINKS}). "
                    f"Add more inline links to authoritative sources."
                )
            if check_h1 != 1:
                issues.append(f"Found {check_h1} H1 headings — exactly 1 is required.")
            if check_h2 < Config.NUM_SECTIONS:
                issues.append(f"Only {check_h2} H2 sections (minimum is {Config.NUM_SECTIONS}).")

            if not issues:
                print(f"  ✓ Self-check passed — {check_words} words, {check_links} links, {check_h1} H1, {check_h2} H2")
                break

            print(f"\n  ⚠ Self-check ({check_attempt + 1}/{MAX_SELF_CHECK_RETRIES + 1}): {len(issues)} issue(s):")
            for issue in issues:
                print(f"    - {issue}")

            if check_attempt >= MAX_SELF_CHECK_RETRIES:
                print(f"  → Self-check limit reached, returning as-is")
                break

            print(f"  → Fixing issues before returning…")
            feedback_lines = "\n".join(f"- {i}" for i in issues)
            draft_escaped = revised_content.replace("{", "{{").replace("}", "}}")
            expand_prompt = ChatPromptTemplate.from_messages([
                ("system", (
                    "You are revising a blog article draft. Fix ONLY the mechanical issues listed below. "
                    "Do not change the topic, tone, or overall structure.\n\n"
                    f"Issues to fix:\n{feedback_lines}\n\n"
                    "Return the complete revised article with all fixes applied."
                )),
                ("human", draft_escaped)
            ])
            expand_chain = expand_prompt | llm | StrOutputParser()
            revised_content = expand_chain.invoke({})

        # Extract inline links
        import re
        md_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', revised_content)
        inline_links = [url for _, url in md_links]

        # Extract title (first H1)
        title_match = re.search(r'^#\s+(.+)$', revised_content, re.MULTILINE)
        article_title = title_match.group(1).strip() if title_match else topic

        # Use code-block-excluding word count for the final report (matches editor)
        word_count = json.loads(analyzer._run(revised_content))["word_count"]

        mode = "Revised" if is_revision else "Generated"
        print(f"\n✓ Article {mode.lower()}")
        print(f"  - Title: {article_title}")
        print(f"  - Word count: {word_count} (excl. code blocks)")
        print(f"  - Inline links: {len(inline_links)}")

        return {
            "article_content": revised_content,
            "article_title": article_title,
            "inline_links": inline_links
        }

    except Exception as e:
        print(f"\n✗ {'Revision' if is_revision else 'Writing'} failed: {str(e)}")
        return {
            "article_content": "",
            "article_title": topic,
            "inline_links": [],
            "errors": state.get("errors", []) + [f"{'Revision' if is_revision else 'Writing'} error: {str(e)}"]
        }
