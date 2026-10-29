"""
Configuration settings for the LangGraph Blog Generation System
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Main configuration class"""

    # ============================================================================
    # LLM Provider Configuration (OpenRouter)
    # ============================================================================

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    # Per-node LLM settings. Which one is sent depends on the model's OpenRouter
    # supported_parameters (see get_llm): "effort" goes out as reasoning.effort
    # when the model supports reasoning and effort isn't "off"; otherwise
    # "temperature" is sent if the model supports it. Thinking and a custom
    # temperature are exclusive, so the two are never sent together.
    REASONING_EFFORTS = ("off", "low", "medium", "high", "xhigh", "max")
    NODE_LLM_DEFAULTS = {
        "query_generator": {"effort": "low", "temperature": 0.1},
        "content_synthesizer": {"effort": "medium", "temperature": 0.1},
        "audience_analysis": {"effort": "low", "temperature": 0.7},
        "writer": {"effort": "high", "temperature": 0.7},
        "fact_checker": {"effort": "high", "temperature": 0.1},
        "editor": {"effort": "high", "temperature": 0.7},
        "seo": {"effort": "low", "temperature": 0.7},
        "formatter": {"effort": "low", "temperature": 0.7},
    }
    # Partial overrides of NODE_LLM_DEFAULTS, e.g. {"writer": {"effort": "xhigh"}}.
    # Set by the API worker from the Settings row before each job.
    NODE_LLM_SETTINGS: dict = {}
    # OpenRouter supported_parameters per model id (None = model not listed),
    # filled once per process by get_model_supported_params().
    _SUPPORTED_PARAMS_CACHE: dict = {}

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
    # Deep Research Settings
    # ============================================================================

    # Deep research configuration
    DEEP_RESEARCH_QUERIES = int(os.getenv("DEEP_RESEARCH_QUERIES", "6"))
    DEEP_RESEARCH_URLS_PER_QUERY = int(os.getenv("DEEP_RESEARCH_URLS_PER_QUERY", "3"))
    DEEP_RESEARCH_MAX_URLS_TOTAL = int(os.getenv("DEEP_RESEARCH_MAX_URLS_TOTAL", "20"))

    # URL fetching limits
    URL_FETCH_TIMEOUT = int(os.getenv("URL_FETCH_TIMEOUT", "30"))

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

    # Writing style and tone
    BLOG_TONE = os.getenv("BLOG_TONE", "informative and insightful")

    # Tone presets - use with --tone preset:<name> (e.g., --tone preset:conversational)
    TONE_PRESETS = {
        "conversational": "friendly, conversational, and approachable — like a knowledgeable friend explaining something they care about, while remaining authoritative and well-researched",
        "expert_casual": "knowledgeable yet informal — like a senior colleague sharing hard-won insights over coffee, mixing technical depth with relatable language",
        "storyteller": "narrative-driven and engaging — weaving real-world stories and examples throughout, making complex topics feel like compelling reads rather than textbooks",
        "practical": "direct, actionable, and results-focused — every paragraph earns its place by teaching the reader something they can use immediately, with minimal fluff",
        "thought_leader": "bold, opinionated, and forward-looking — taking clear positions on industry trends, challenging conventional wisdom, and backing claims with evidence",
    }

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
    # Table of Contents Settings
    # ============================================================================

    INCLUDE_TABLE_OF_CONTENTS = os.getenv("INCLUDE_TABLE_OF_CONTENTS", "true").lower() == "true"
    TOC_INCLUDE_H3 = os.getenv("TOC_INCLUDE_H3", "false").lower() == "true"
    TOC_MIN_SECTIONS = int(os.getenv("TOC_MIN_SECTIONS", "3"))

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

        if not cls.OPENROUTER_API_KEY:
            errors.append("OPENROUTER_API_KEY is required")

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
    def merge_node_llm_settings(cls, stored: dict, updates: dict) -> dict:
        """
        Validate partial per-node LLM updates and merge them into stored overrides.

        Args:
            stored: Existing overrides, {node: {"effort"?: str, "temperature"?: float}}
            updates: New partial overrides in the same shape

        Returns:
            A new dict with updates merged over stored, per node and per key

        Raises:
            ValueError: On an unknown node, unknown key, or out-of-range value
        """
        for node, values in updates.items():
            if node not in cls.NODE_LLM_DEFAULTS:
                raise ValueError(f"Unknown LLM node '{node}'. Valid nodes: {', '.join(cls.NODE_LLM_DEFAULTS)}")
            if not isinstance(values, dict):
                raise ValueError(f"Settings for node '{node}' must be an object")
            unknown = set(values) - {"effort", "temperature"}
            if unknown:
                raise ValueError(f"Unknown setting(s) for node '{node}': {', '.join(sorted(unknown))}")
            if "effort" in values and values["effort"] not in cls.REASONING_EFFORTS:
                raise ValueError(f"effort for '{node}' must be one of: {', '.join(cls.REASONING_EFFORTS)}")
            if "temperature" in values:
                t = values["temperature"]
                if isinstance(t, bool) or not isinstance(t, (int, float)) or not (0.0 <= t <= 2.0):
                    raise ValueError(f"temperature for '{node}' must be between 0.0 and 2.0")
        merged = {node: dict(values) for node, values in stored.items()}
        for node, values in updates.items():
            merged[node] = {**merged.get(node, {}), **values}
        return merged

    @classmethod
    def get_node_llm_settings(cls, overrides: Optional[dict] = None) -> dict:
        """
        Get effective per-node LLM settings (defaults merged with overrides).

        Args:
            overrides: Partial overrides; defaults to NODE_LLM_SETTINGS

        Returns:
            Dict of node name to {"effort": str, "temperature": float}
        """
        overrides = cls.NODE_LLM_SETTINGS if overrides is None else overrides
        return {
            node: {**defaults, **overrides.get(node, {})}
            for node, defaults in cls.NODE_LLM_DEFAULTS.items()
        }

    @classmethod
    def get_llm(cls, node: str):
        """
        Get LLM via OpenRouter, configured for a pipeline node.

        Args:
            node: Key of NODE_LLM_DEFAULTS whose effort/temperature to use

        Returns:
            ChatOpenRouter instance
        """
        from langchain_openrouter import ChatOpenRouter

        settings = cls.get_node_llm_settings()[node]
        params = cls.get_model_supported_params()

        def supports(param: str) -> bool:
            # Unknown capabilities: send whatever the node is configured for
            return params is None or param in params

        kwargs = {"model": cls.OPENROUTER_MODEL}
        if settings["effort"] != "off" and supports("reasoning"):
            kwargs["reasoning"] = {"effort": settings["effort"]}
        elif supports("temperature"):
            kwargs["temperature"] = settings["temperature"]
        return ChatOpenRouter(**kwargs)

    @classmethod
    def get_model_supported_params(cls) -> Optional[set]:
        """
        Get OpenRouter's supported_parameters for OPENROUTER_MODEL.

        Fetches the public model list once per process and caches it.

        Returns:
            Set of parameter names (e.g. {"reasoning", "temperature"}), or None
            if the list can't be fetched or the model isn't in it
        """
        model = cls.OPENROUTER_MODEL
        if model in cls._SUPPORTED_PARAMS_CACHE:
            return cls._SUPPORTED_PARAMS_CACHE[model]

        import requests

        try:
            resp = requests.get(f"{cls.OPENROUTER_BASE_URL}/models", timeout=15)
            resp.raise_for_status()
            data = resp.json()["data"]
        except (requests.RequestException, ValueError, KeyError) as e:
            # Not cached, so the next get_llm() call retries
            print(f"Warning: could not fetch OpenRouter model capabilities ({e}); "
                  f"sending effort/temperature as configured")
            return None

        for m in data:
            cls._SUPPORTED_PARAMS_CACHE[m["id"]] = set(m.get("supported_parameters", []))
        if model not in cls._SUPPORTED_PARAMS_CACHE:
            print(f"Warning: model '{model}' not in OpenRouter's model list; "
                  f"sending effort/temperature as configured")
            cls._SUPPORTED_PARAMS_CACHE[model] = None
        return cls._SUPPORTED_PARAMS_CACHE[model]

    @classmethod
    def get_llm_info(cls) -> dict:
        """
        Get information about the configured LLM for display purposes.

        Returns:
            Dict with provider info
        """
        return {
            "primary": {
                "provider": "OpenRouter",
                "model": cls.OPENROUTER_MODEL,
            }
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
