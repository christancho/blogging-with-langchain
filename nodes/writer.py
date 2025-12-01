"""
Writer node for creating blog content
"""
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from nodes.prompt_loader import PromptLoader


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

    # Initialize LLM
    llm = Config.get_llm()

    # Check if this is a revision
    is_revision = revision_count > 0 and approval_feedback

    if is_revision:
        # REVISION MODE - Use feedback from editor
        print(f"REVISION MODE - Attempt {revision_count}")
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

        # Use revision prompt
        revision_template = PromptLoader.load("revision")
        revision_prompt = revision_template.render(
            topic=topic,
            article_content=article_content_escaped,
            editor_feedback=feedback_escaped
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

        # Use standard writer prompt
        writer_template = PromptLoader.load("writer")
        writer_prompt = writer_template.render(
            topic=topic,
            tone=Config.BLOG_TONE,
            instructions=instructions,
            research_summary=research_summary
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

        # Extract inline links
        import re
        md_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', revised_content)
        inline_links = [url for _, url in md_links]

        # Extract title (first H1)
        title_match = re.search(r'^#\s+(.+)$', revised_content, re.MULTILINE)
        article_title = title_match.group(1).strip() if title_match else topic

        # Count words
        word_count = len(revised_content.split())

        mode = "Revised" if is_revision else "Generated"
        print(f"\n✓ Article {mode.lower()}")
        print(f"  - Title: {article_title}")
        print(f"  - Word count: {word_count}")
        print(f"  - Inline links: {len(inline_links)}")

        return {
            "article_content": revised_content,
            "article_title": article_title,
            "inline_links": inline_links,
        }

    except Exception as e:
        print(f"\n✗ {'Revision' if is_revision else 'Writing'} failed: {str(e)}")
        return {
            "article_content": "",
            "article_title": topic,
            "inline_links": [],
            "errors": state.get("errors", []) + [f"{'Revision' if is_revision else 'Writing'} error: {str(e)}"]
        }
