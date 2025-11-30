"""
LangGraph state graph for blog generation workflow
"""
from langgraph.graph import StateGraph, END
from state import BlogState
from nodes import research_node, writer_node, seo_node, formatter_node, editor_node, publisher_node


def create_blog_graph():
    """
    Create and compile the blog generation state graph

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

    # Define the workflow edges (sequential for now)
    workflow.add_edge("research", "writer")
    workflow.add_edge("writer", "seo")
    workflow.add_edge("seo", "formatter")
    workflow.add_edge("formatter", "editor")
    workflow.add_edge("editor", "publisher")
    workflow.add_edge("publisher", END)

    # Set the entry point
    workflow.set_entry_point("research")

    # Compile the graph
    app = workflow.compile()

    return app


# Create the graph instance
blog_graph = create_blog_graph()


def generate_blog_post(topic: str, instructions: str = None) -> dict:
    """
    Generate a complete blog post on the given topic

    Args:
        topic: The blog topic to write about
        instructions: Optional custom instructions for the article (e.g., style, audience, focus areas)

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
        "errors": [],
        "warnings": [],
        "workflow_version": "1.0.0"
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
