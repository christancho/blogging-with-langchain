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
        "USE_PRIMARY_LLM": "true"
    })
    def test_get_llm_config_anthropic(self):
        """Test LLM config for Anthropic"""
        # Reload config to pick up env vars
        from importlib import reload
        import config
        reload(config)

        llm_config = config.Config.get_llm_config()

        assert llm_config["provider"] == "anthropic"
        assert llm_config["model"] == "claude-3-5-sonnet-20241022"

    @patch.dict(os.environ, {
        "OPENROUTER_API_KEY": "test_key",
        "OPENROUTER_MODEL": "anthropic/claude-3.5-sonnet",
        "USE_PRIMARY_LLM": "false"
    })
    def test_get_llm_config_openrouter(self):
        """Test LLM config for OpenRouter"""
        from importlib import reload
        import config
        reload(config)

        llm_config = config.Config.get_llm_config()

        assert llm_config["provider"] == "openrouter"
        assert llm_config["base_url"] == "https://openrouter.ai/api/v1"

    def test_default_tags(self):
        """Test default tags configuration"""
        assert "blog" in Config.DEFAULT_TAGS
        assert "auto-generated" in Config.DEFAULT_TAGS

    def test_publish_as_draft_default(self):
        """Test default publish as draft setting"""
        assert Config.PUBLISH_AS_DRAFT is True
