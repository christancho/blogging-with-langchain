"""
Unit tests for configuration
"""
import pytest
import os
from unittest.mock import MagicMock, patch

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

    @pytest.mark.parametrize("params, overrides, expected", [
        # Model supports both: effort wins unless the node is "off"
        ({"reasoning", "temperature"}, {}, {"reasoning": {"effort": "high"}}),
        ({"reasoning", "temperature"}, {"effort": "off", "temperature": 0.3}, {"temperature": 0.3}),
        # Reasoning only: "off" sends neither (model default)
        ({"reasoning"}, {}, {"reasoning": {"effort": "high"}}),
        ({"reasoning"}, {"effort": "off"}, {}),
        # Temperature only: effort is ignored
        ({"temperature"}, {}, {"temperature": 0.1}),
        # Neither supported
        (set(), {}, {}),
        # Capabilities unknown: send what the node is configured for
        (None, {}, {"reasoning": {"effort": "high"}}),
        (None, {"effort": "off"}, {"temperature": 0.1}),
    ])
    def test_get_llm_follows_model_capabilities(self, params, overrides, expected):
        """get_llm() sends effort or temperature based on what the model supports."""
        with patch("langchain_openrouter.ChatOpenRouter") as mock_chat, \
                patch.object(Config, "NODE_LLM_SETTINGS", {"fact_checker": overrides}), \
                patch.object(Config, "get_model_supported_params", return_value=params):
            Config.get_llm("fact_checker")
            kwargs = dict(mock_chat.call_args.kwargs)
            kwargs.pop("model")
            assert kwargs == expected

    def test_get_model_supported_params_caches_list(self):
        """The list is fetched once per uncached model; unlisted models cache as None."""
        fake = MagicMock()
        fake.json.return_value = {"data": [{"id": "a/x", "supported_parameters": ["reasoning"]}]}
        with patch("requests.get", return_value=fake) as mock_get, \
                patch.object(Config, "_SUPPORTED_PARAMS_CACHE", {}), \
                patch.object(Config, "OPENROUTER_MODEL", "a/x"):
            assert Config.get_model_supported_params() == {"reasoning"}
            assert Config.get_model_supported_params() == {"reasoning"}
            assert mock_get.call_count == 1
            with patch.object(Config, "OPENROUTER_MODEL", "a/missing"):
                assert Config.get_model_supported_params() is None
                assert Config.get_model_supported_params() is None
            assert mock_get.call_count == 2

    def test_get_model_supported_params_fetch_error(self, capsys):
        """A failed fetch returns None, warns, and isn't cached."""
        import requests
        with patch("requests.get", side_effect=requests.ConnectionError("down")), \
                patch.object(Config, "_SUPPORTED_PARAMS_CACHE", {}) as cache:
            assert Config.get_model_supported_params() is None
            assert cache == {}
        assert "could not fetch OpenRouter model capabilities" in capsys.readouterr().out

    def test_get_llm_unknown_node_raises(self):
        """get_llm() rejects a node name with no settings."""
        with pytest.raises(KeyError):
            Config.get_llm("nonexistent")

    def test_get_node_llm_settings_merges_overrides(self):
        """Overrides replace only the keys they set; other nodes keep defaults."""
        merged = Config.get_node_llm_settings({"writer": {"effort": "xhigh"}})
        assert merged["writer"] == {"effort": "xhigh", "temperature": 0.7}
        assert merged["seo"] == Config.NODE_LLM_DEFAULTS["seo"]

    def test_merge_node_llm_settings(self):
        """merge_node_llm_settings merges per key and does not mutate its inputs."""
        stored = {"writer": {"effort": "xhigh"}}
        merged = Config.merge_node_llm_settings(stored, {"writer": {"temperature": 1.0}, "seo": {"effort": "off"}})
        assert merged == {"writer": {"effort": "xhigh", "temperature": 1.0}, "seo": {"effort": "off"}}
        assert stored == {"writer": {"effort": "xhigh"}}

    @pytest.mark.parametrize("updates", [
        {"bogus": {"effort": "low"}},
        {"writer": {"effort": "extreme"}},
        {"writer": {"temperature": 2.5}},
        {"writer": {"temperature": "hot"}},
        {"writer": {"top_p": 0.9}},
        {"writer": "high"},
    ])
    def test_merge_node_llm_settings_rejects_invalid(self, updates):
        """Invalid nodes, keys, and values raise ValueError."""
        with pytest.raises(ValueError):
            Config.merge_node_llm_settings({}, updates)
