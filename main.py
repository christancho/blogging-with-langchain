"""
Main entry point for the LangGraph Blog Generation System

Usage:
    python main.py "Your blog topic here"
    python main.py "AI and Machine Learning in Healthcare"
"""
import sys
import argparse
from datetime import datetime

from graph import generate_blog_post, visualize_graph
from config import Config


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate a blog post using LangGraph and Claude/OpenRouter"
    )
    parser.add_argument(
        "topic",
        type=str,
        nargs="?",
        help="The blog topic to write about"
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Generate a visualization of the workflow graph"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose output"
    )
    parser.add_argument(
        "--tone",
        type=str,
        default=None,
        help='Override the blog tone (e.g., "conversational and engaging", "technical and detailed")'
    )

    args = parser.parse_args()

    # Handle visualization request
    if args.visualize:
        print("Generating workflow visualization...")
        visualize_graph()
        return

    # Check if topic is provided
    if not args.topic:
        print("Error: Blog topic is required")
        print("\nUsage:")
        print("  python main.py \"Your blog topic here\"")
        print("\nExamples:")
        print("  python main.py \"AI and Machine Learning in Healthcare\"")
        print("  python main.py \"Introduction to LangChain and LangGraph\"")
        print("  python main.py \"Best Practices for Python Web Development\"")
        print("\nOptions:")
        print("  --visualize    Generate a visualization of the workflow graph")
        print("  --debug        Enable debug mode")
        print('  --tone         Override blog tone (e.g., "conversational and engaging")')
        sys.exit(1)

    topic = args.topic

    # Override tone if provided via CLI
    if args.tone:
        Config.BLOG_TONE = args.tone

    # Print configuration info
    print("\n" + "="*80)
    print("BLOG GENERATION SYSTEM")
    print("="*80)
    print(f"LLM Provider: {Config.get_llm_config()['provider'].upper()}")
    print(f"Model: {Config.get_llm_config()['model']}")
    print(f"Target Word Count: {Config.WORD_COUNT_TARGET}")
    print(f"Min Inline Links: {Config.MIN_INLINE_LINKS}")
    print(f"Blog Tone: {Config.BLOG_TONE}")
    print(f"Publish as Draft: {Config.PUBLISH_AS_DRAFT}")

    # Show LangSmith status
    if Config.is_langsmith_enabled():
        print(f"🔍 LangSmith Tracing: ENABLED (Project: {Config.LANGCHAIN_PROJECT})")
    else:
        print(f"🔍 LangSmith Tracing: DISABLED")

    print("="*80)

    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        print(f"\n❌ Configuration Error:")
        print(f"   {e}")
        print("\nPlease check your .env file and ensure all required API keys are set.")
        sys.exit(1)

    # Generate the blog post
    start_time = datetime.now()

    try:
        final_state = generate_blog_post(topic)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n⏱️  Total execution time: {duration:.1f} seconds")

        # Check for errors
        errors = final_state.get('errors', [])
        if errors:
            print(f"\n⚠️  Completed with {len(errors)} error(s)")
            return 1

        print(f"\n✅ Blog post generated successfully!")
        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Generation interrupted by user")
        return 130

    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
