"""
Configuration settings for the LangGraph Blog Generation System
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Main configuration class"""

    # ============================================================================
    # LLM Provider Configuration (Claude Primary, OpenRouter Fallback)
    # ============================================================================

    # Primary: Anthropic Claude
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    CLAUDE_TEMPERATURE = float(os.getenv("CLAUDE_TEMPERATURE", "0.7"))

    # Fallback: OpenRouter
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    # LLM Selection
    USE_PRIMARY = os.getenv("USE_PRIMARY_LLM", "true").lower() == "true"

    # ============================================================================
    # LangSmith Configuration (Optional - for tracing and debugging)
    # ============================================================================

    LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
    LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "blog-generation")
    LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

    # ============================================================================
    # Search API Configuration
    # ============================================================================

    BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
    BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

    # ============================================================================
    # Ghost CMS Configuration
    # ============================================================================

    GHOST_API_KEY = os.getenv("GHOST_API_KEY")
    GHOST_API_URL = os.getenv("GHOST_API_URL")
    GHOST_AUTHOR_ID = os.getenv("GHOST_AUTHOR_ID")

    # ============================================================================
    # Blog Content Settings
    # ============================================================================

    # Word count target
    WORD_COUNT_TARGET = int(os.getenv("WORD_COUNT_TARGET", "3500"))

    # Article structure
    NUM_SECTIONS = int(os.getenv("NUM_SECTIONS", "4"))
    INCLUDE_INTRO = True
    INCLUDE_CONCLUSION = True

    # Links and references
    MIN_INLINE_LINKS = int(os.getenv("MIN_INLINE_LINKS", "10"))
    MAX_INLINE_LINKS = int(os.getenv("MAX_INLINE_LINKS", "15"))

    # ============================================================================
    # SEO Settings
    # ============================================================================

    # Keyword optimization
    TARGET_KEYWORD_DENSITY = float(os.getenv("TARGET_KEYWORD_DENSITY", "1.5"))

    # Meta data lengths
    SEO_TITLE_MIN_LENGTH = int(os.getenv("SEO_TITLE_MIN_LENGTH", "50"))
    SEO_TITLE_MAX_LENGTH = int(os.getenv("SEO_TITLE_MAX_LENGTH", "60"))
    META_DESCRIPTION_MIN_LENGTH = int(os.getenv("META_DESCRIPTION_MIN_LENGTH", "150"))
    META_DESCRIPTION_MAX_LENGTH = int(os.getenv("META_DESCRIPTION_MAX_LENGTH", "160"))

    # Tags
    MIN_TAGS = int(os.getenv("MIN_TAGS", "5"))
    MAX_TAGS = int(os.getenv("MAX_TAGS", "8"))

    # ============================================================================
    # Output Settings
    # ============================================================================

    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
    OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "markdown")
    SAVE_INTERMEDIATE_OUTPUTS = os.getenv("SAVE_INTERMEDIATE_OUTPUTS", "false").lower() == "true"

    # ============================================================================
    # Ghost Publishing Settings
    # ============================================================================

    PUBLISH_AS_DRAFT = os.getenv("PUBLISH_AS_DRAFT", "true").lower() == "true"
    DEFAULT_TAGS = os.getenv("DEFAULT_TAGS", "blog,auto-generated").split(",")

    # ============================================================================
    # Validation
    # ============================================================================

    @classmethod
    def validate(cls) -> None:
        """Validate that all required configuration is present"""
        errors = []

        # Check LLM configuration
        if cls.USE_PRIMARY and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is required when using primary LLM")

        if not cls.USE_PRIMARY and not cls.OPENROUTER_API_KEY:
            errors.append("OPENROUTER_API_KEY is required when using fallback LLM")

        # Check required APIs
        if not cls.BRAVE_SEARCH_API_KEY:
            errors.append("BRAVE_SEARCH_API_KEY is required")

        if not cls.GHOST_API_KEY:
            errors.append("GHOST_API_KEY is required")

        if not cls.GHOST_API_URL:
            errors.append("GHOST_API_URL is required")

        if errors:
            raise ValueError(
                "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
            )

    @classmethod
    def get_llm_config(cls) -> dict:
        """Get the active LLM configuration"""
        if cls.USE_PRIMARY:
            return {
                "provider": "anthropic",
                "api_key": cls.ANTHROPIC_API_KEY,
                "model": cls.CLAUDE_MODEL,
                "temperature": cls.CLAUDE_TEMPERATURE,
            }
        else:
            return {
                "provider": "openrouter",
                "api_key": cls.OPENROUTER_API_KEY,
                "model": cls.OPENROUTER_MODEL,
                "base_url": cls.OPENROUTER_BASE_URL,
                "temperature": cls.CLAUDE_TEMPERATURE,
            }

    @classmethod
    def setup_langsmith(cls) -> None:
        """
        Setup LangSmith tracing environment variables

        This enables automatic tracing of LangChain/LangGraph operations
        to LangSmith for debugging and monitoring.
        """
        if cls.LANGCHAIN_TRACING_V2 and cls.LANGCHAIN_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = cls.LANGCHAIN_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = cls.LANGCHAIN_PROJECT
            os.environ["LANGCHAIN_ENDPOINT"] = cls.LANGCHAIN_ENDPOINT

    @classmethod
    def is_langsmith_enabled(cls) -> bool:
        """Check if LangSmith tracing is enabled"""
        return cls.LANGCHAIN_TRACING_V2 and bool(cls.LANGCHAIN_API_KEY)


# Validate configuration on import
try:
    Config.validate()
except ValueError as e:
    print(f"Warning: {e}")
    print("Please ensure your .env file is properly configured.")

# Setup LangSmith tracing if enabled
Config.setup_langsmith()
