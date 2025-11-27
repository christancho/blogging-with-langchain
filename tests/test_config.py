"""
Unit tests for configuration
"""
import pytest
import os
from unittest.mock import patch

from config import Config


class TestConfig:
    """Tests for Config class"""

    def test_default_values(self):
        """Test that default values are set"""
        assert Config.WORD_COUNT_TARGET == 3500
        assert Config.NUM_SECTIONS == 4
        assert Config.MIN_INLINE_LINKS == 10
        assert Config.TARGET_KEYWORD_DENSITY == 1.5

    def test_output_directory(self):
        """Test output directory default"""
        assert Config.OUTPUT_DIR == "output"

    def test_seo_settings(self):
        """Test SEO configuration"""
        assert Config.SEO_TITLE_MIN_LENGTH == 50
        assert Config.SEO_TITLE_MAX_LENGTH == 60
        assert Config.META_DESCRIPTION_MIN_LENGTH == 150
        assert Config.META_DESCRIPTION_MAX_LENGTH == 160

    @patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "test_key",
        "CLAUDE_MODEL": "claude-3-5-sonnet-20241022",
    })
    def test_get_llm_info_anthropic_only(self):
        """Test LLM info when only Anthropic is configured"""
        from importlib import reload
        import config
        reload(config)

        llm_info = config.Config.get_llm_info()

        assert "primary" in llm_info
        assert llm_info["primary"]["provider"] == "Anthropic"
        assert llm_info["primary"]["model"] == "claude-3-5-sonnet-20241022"
        assert "fallback" not in llm_info

    @patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "test_anthropic_key",
        "OPENROUTER_API_KEY": "test_openrouter_key",
        "CLAUDE_MODEL": "claude-3-5-sonnet-20241022",
        "OPENROUTER_MODEL": "openai/gpt-4o"
    })
    def test_get_llm_info_both_providers(self):
        """Test LLM info when both providers are configured"""
        from importlib import reload
        import config
        reload(config)

        llm_info = config.Config.get_llm_info()

        assert "primary" in llm_info
        assert llm_info["primary"]["provider"] == "Anthropic"
        assert llm_info["primary"]["model"] == "claude-3-5-sonnet-20241022"

        assert "fallback" in llm_info
        assert llm_info["fallback"]["provider"] == "OpenRouter"
        assert llm_info["fallback"]["model"] == "openai/gpt-4o"

    @patch.dict(os.environ, {
        "OPENROUTER_API_KEY": "test_key",
        "OPENROUTER_MODEL": "openai/gpt-4o",
    })
    def test_get_llm_info_openrouter_only(self):
        """Test LLM info when only OpenRouter is configured"""
        from importlib import reload
        import config
        reload(config)

        llm_info = config.Config.get_llm_info()

        assert "primary" in llm_info
        assert llm_info["primary"]["provider"] == "OpenRouter"
        assert llm_info["primary"]["model"] == "openai/gpt-4o"
        assert "fallback" not in llm_info

    def test_default_tags(self):
        """Test default tags configuration"""
        assert "blog" in Config.DEFAULT_TAGS
        assert "auto-generated" in Config.DEFAULT_TAGS

    def test_publish_as_draft_default(self):
        """Test default publish as draft setting"""
        assert Config.PUBLISH_AS_DRAFT is True
