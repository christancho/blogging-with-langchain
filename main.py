"""
Main entry point for the LangGraph Blog Generation System

Usage:
    Interactive mode:
        python main.py

    Command-line mode:
        python main.py "Your blog topic here"
        python main.py "AI and Machine Learning in Healthcare"
"""
import sys
import argparse

from datetime import datetime
from graph import generate_blog_post, visualize_graph
from config import Config


def interactive_mode():
    """
    Interactive mode for gathering blog generation parameters

    Returns:
        tuple: (topic, instructions, tone) or None if cancelled
    """
    print("\n" + "="*80)
    print("BLOG GENERATION SYSTEM - Interactive Mode")
    print("="*80)
    print("\nPress Ctrl+C at any time to cancel\n")

    try:
        # Get topic (required)
        print("📝 Blog Topic (required)")
        print("   Example: 'Building Your First MCP Server: A Practical Tutorial'")
        topic = input("   > ").strip()

        if not topic:
            print("\n❌ Topic is required!")
            return None

        # Get instructions (optional)
        print("\n📋 Custom Instructions (optional, press Enter to skip)")
        print("   Example: 'Use this repo as reference: https://github.com/...'")
        print("   Tip: You can paste long instructions with URLs")
        instructions_input = input("   > ").strip()
        instructions = instructions_input if instructions_input else None

        # Get tone (optional)
        print(f"\n🎨 Blog Tone (optional, press Enter for default: '{Config.BLOG_TONE}')")
        print("   Example: 'conversational and engaging' or 'technical and detailed'")
        tone_input = input("   > ").strip()
        tone = tone_input if tone_input else None

        # Get word count target (optional)
        print(f"\n📊 Word Count Target (optional, press Enter for default: {Config.WORD_COUNT_TARGET})")
        print("   Example: 5000")
        word_count_input = input("   > ").strip()
        word_count_target = int(word_count_input) if word_count_input else None

        # Show summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Topic:        {topic}")
        print(f"Instructions: {instructions[:60] + '...' if instructions and len(instructions) > 60 else instructions or '(none)'}")
        print(f"Tone:         {tone or f'{Config.BLOG_TONE} (default)'}")
        print(f"Word Count:   {word_count_target or f'{Config.WORD_COUNT_TARGET} (default)'}")
        print("="*80)

        # Confirm
        confirm = input("\n▶️  Start generation? [Y/n]: ").strip().lower()
        if confirm and confirm not in ['y', 'yes']:
            print("\n❌ Cancelled by user")
            return None

        return topic, instructions, tone, word_count_target

    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        return None
    except EOFError:
        print("\n\n❌ Cancelled by user")
        return None

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
    parser.add_argument(
        "--instructions",
        "-i",
        type=str,
        default=None,
        help='Custom instructions for the article (e.g., "Focus on examples for beginners", "Target C-level executives")'
    )
    parser.add_argument(
        "--word-count",
        type=int,
        default=None,
        help=f'Target word count for the article (default: {Config.WORD_COUNT_TARGET})'
    )

    args = parser.parse_args()

    # Handle visualization request
    if args.visualize:
        print("Generating workflow visualization...")
        visualize_graph()
        return

    # Interactive mode vs CLI mode
    if not args.topic:
        # No topic provided - enter interactive mode
        result = interactive_mode()
        if result is None:
            return 1  # User cancelled

        topic, instructions, tone, word_count_target = result
    else:
        # CLI mode - use provided arguments
        topic = args.topic
        instructions = args.instructions
        tone = args.tone
        word_count_target = args.word_count

    # Print configuration info
    print("\n" + "="*80)
    print("BLOG GENERATION SYSTEM")
    print("="*80)

    # Display LLM configuration
    llm_info = Config.get_llm_info()
    if "primary" in llm_info:
        print(f"Primary LLM: {llm_info['primary']['provider']} ({llm_info['primary']['model']})")
    if "fallback" in llm_info:
        print(f"Fallback LLM: {llm_info['fallback']['provider']} ({llm_info['fallback']['model']})")

    print(f"Target Word Count: {word_count_target or Config.WORD_COUNT_TARGET}")
    print(f"Min Inline Links: {Config.MIN_INLINE_LINKS}")
    print(f"Blog Tone: {tone or Config.BLOG_TONE}")
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
        final_state = generate_blog_post(topic, instructions, tone, word_count_target)

        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()
        duration_minutes = duration_seconds / 60

        print(f"\n⏱️  Total execution time: {duration_minutes:.1f} minutes ({duration_seconds:.0f} seconds)")

        # Show LangSmith info for cost tracking
        if Config.is_langsmith_enabled():
            print(f"\n💰 Cost tracking: View detailed token usage and costs in LangSmith")
            print(f"   Project: {Config.LANGCHAIN_PROJECT}")
            print(f"   URL: https://smith.langchain.com")

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
