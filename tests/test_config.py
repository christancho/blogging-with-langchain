"""
Unit tests for configuration
"""
import pytest
import os
from unittest.mock import patch

from agentic.config import Config


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
        "OPENROUTER_API_KEY": "test_key",
        "OPENROUTER_MODEL": "anthropic/claude-sonnet-4-5",
    })
    def test_get_llm_info(self):
        """Test LLM info returns OpenRouter provider"""
        from importlib import reload
        import agentic.config as config
        reload(config)

        llm_info = config.Config.get_llm_info()

        assert "primary" in llm_info
        assert llm_info["primary"]["provider"] == "OpenRouter"
        assert llm_info["primary"]["model"] == "anthropic/claude-sonnet-4-5"
        assert "fallback" not in llm_info

    def test_default_tags(self):
        """Test default tags configuration"""
        assert "blog" in Config.DEFAULT_TAGS
        assert "auto-generated" in Config.DEFAULT_TAGS

    def test_publish_as_draft_default(self):
        """Test default publish as draft setting"""
        assert Config.PUBLISH_AS_DRAFT is True

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"})
    def test_get_llm_temperature_override(self):
        """get_llm() uses the provided temperature when given, not the default."""
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            Config.get_llm(temperature=0.1)
            assert mock_chat.call_args.kwargs["temperature"] == 0.1

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"})
    def test_get_llm_default_temperature(self):
        """get_llm() falls back to OPENROUTER_TEMPERATURE when no override given."""
        with patch("langchain_openai.ChatOpenAI") as mock_chat:
            Config.get_llm()
            assert mock_chat.call_args.kwargs["temperature"] == Config.OPENROUTER_TEMPERATURE

    def test_research_temperature_default(self):
        """RESEARCH_TEMPERATURE defaults to 0.1."""
        assert Config.RESEARCH_TEMPERATURE == 0.1
