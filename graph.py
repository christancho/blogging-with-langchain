"""
LangGraph state graph for blog generation workflow
"""
from langgraph.graph import StateGraph, END
from state import BlogState
from config import Config
from nodes import research_node, writer_node, seo_node, formatter_node, editor_node, publisher_node


def route_editor_decision(state: BlogState) -> str:
    """
    Route the workflow based on editor approval decision

    Args:
        state: Current blog state

    Returns:
        Route key: "publisher" (approved content -> publishing) or "writer" (rejected -> revision)
    """
    approval_status = state.get("approval_status", "pending")
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)

    # If approved or forced publish - route to publisher
    if approval_status in ["approved", "force_publish"]:
        return "publisher"

    # If rejected and revisions available - route back to writer for revision
    if approval_status == "rejected" and revision_count < max_revisions:
        return "writer"

    # Default: if we somehow get here, approve and publish (shouldn't happen)
    return "publisher"


def create_blog_graph():
    """
    Create and compile the blog generation state graph with approval gate and revision loop

    Returns:
        Compiled StateGraph application
    """
    # Initialize the graph
    workflow = StateGraph(BlogState)

    # Add all nodes
    workflow.add_node("research", research_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("seo", seo_node)
    workflow.add_node("formatter", formatter_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("publisher", publisher_node)

    # Define the workflow edges
    # New order: research -> writer -> formatter -> seo -> editor -> publisher
    workflow.add_edge("research", "writer")
    workflow.add_edge("writer", "formatter")
    workflow.add_edge("formatter", "seo")
    workflow.add_edge("seo", "editor")

    # Conditional edge based on editor decision
    # If approved or force_publish -> publisher
    # If rejected with revisions available -> writer (for revision loop)
    workflow.add_conditional_edges(
        "editor",
        route_editor_decision,
        {
            "publisher": "publisher",  # Approved/force_publish -> go to publisher
            "writer": "writer"         # Rejected -> go back to writer for revision
        }
    )

    workflow.add_edge("publisher", END)

    # Set the entry point
    workflow.set_entry_point("research")

    # Compile the graph
    app = workflow.compile()

    return app


# Create the graph instance
blog_graph = create_blog_graph()


def generate_blog_post(
    topic: str,
    instructions: str = None,
    tone: str = None,
    word_count_target: int = None
) -> dict:
    """
    Generate a complete blog post on the given topic

    Args:
        topic: The blog topic to write about
        instructions: Optional custom instructions for the article (e.g., style, audience, focus areas)
        tone: Optional blog tone override (default: Config.BLOG_TONE)
        word_count_target: Optional word count target (default: Config.WORD_COUNT_TARGET)

    Returns:
        Final state dictionary with all results
    """
    print("\n" + "="*80)
    print(f"STARTING BLOG GENERATION WORKFLOW")
    print(f"Topic: {topic}")
    if instructions:
        print(f"Instructions: {instructions[:100]}..." if len(instructions) > 100 else f"Instructions: {instructions}")
    print("="*80)

    # Initialize state
    initial_state = {
        "topic": topic,
        "instructions": instructions,
        "tone": tone or Config.BLOG_TONE,
        "word_count_target": word_count_target or Config.WORD_COUNT_TARGET,
        "errors": [],
        "warnings": [],
        "workflow_version": "1.0.0",
        "approval_status": "pending",
        "revision_count": 0,
        "max_revisions": 3
    }

    # Run the graph
    final_state = blog_graph.invoke(initial_state)

    print("\n" + "="*80)
    print("WORKFLOW COMPLETED")
    print("="*80)

    # Print summary
    print_summary(final_state)

    return final_state


def print_summary(state: dict):
    """
    Print a summary of the workflow results

    Args:
        state: Final state dictionary
    """
    print("\n📝 BLOG POST SUMMARY:")
    print(f"  - Topic: {state.get('topic', 'N/A')}")
    print(f"  - Title: {state.get('seo_title', state.get('article_title', 'N/A'))}")
    print(f"  - Word Count: {len(state.get('final_content', '').split())} words")
    print(f"  - Quality Score: {state.get('quality_score', 0.0)}")
    print(f"  - Links: {len(state.get('inline_links', []))}")
    print(f"  - Tags: {', '.join(state.get('tags', []))}")

    # Publication status
    pub_status = state.get('publication_status', 'unknown')
    if pub_status == 'draft':
        print(f"\n✅ Published as draft")
        if state.get('ghost_post_url'):
            print(f"   URL: {state['ghost_post_url']}")
    elif pub_status == 'published':
        print(f"\n✅ Published")
        if state.get('ghost_post_url'):
            print(f"   URL: {state['ghost_post_url']}")
    elif pub_status == 'failed':
        print(f"\n❌ Publication failed")

    # Errors/warnings
    errors = state.get('errors', [])
    warnings = state.get('warnings', [])

    if errors:
        print(f"\n❌ Errors ({len(errors)}):")
        for error in errors:
            print(f"   - {error}")

    if warnings:
        print(f"\n⚠️  Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"   - {warning}")


# For debugging: visualize the graph
def visualize_graph(output_file: str = None):
    """
    Generate a visual representation of the graph

    Args:
        output_file: Output filename for the graph image (default: media/blog_graph.png)
    """
    import os

    # Default to media/blog_graph.png
    if output_file is None:
        output_file = "media/blog_graph.png"

    try:
        from IPython.display import Image, display

        # Create media directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Get the graph visualization
        graph_image = blog_graph.get_graph().draw_mermaid_png()

        # Save to file
        with open(output_file, 'wb') as f:
            f.write(graph_image)

        print(f"✅ Graph visualization saved to {output_file}")

        # Try to display in notebook
        try:
            display(Image(graph_image))
        except:
            pass

    except ImportError as e:
        print("\n❌ Visualization requires additional dependencies:")
        print("   - graphviz (Python package)")
        print("   - IPython (for notebook display)")
        print("\nInstall with:")
        print("   pip install graphviz")
        print("\nYou may also need the system graphviz package:")
        print("   macOS:  brew install graphviz")
        print("   Ubuntu: sudo apt-get install graphviz")
        print("   CentOS: sudo yum install graphviz")
        print(f"\nError details: {e}")
    except Exception as e:
        print(f"❌ Could not generate visualization: {e}")
