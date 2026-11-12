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
                patch.object(Config, "_SUPPORTED_PARAMS_CACHE", {}):
            assert Config.get_model_supported_params("a/x") == {"reasoning"}
            assert Config.get_model_supported_params("a/x") == {"reasoning"}
            assert mock_get.call_count == 1
            assert Config.get_model_supported_params("a/missing") is None
            assert Config.get_model_supported_params("a/missing") is None
            assert mock_get.call_count == 2

    def test_get_model_supported_params_fetch_error(self, capsys):
        """A failed fetch returns None, warns, and isn't cached."""
        import requests
        with patch("requests.get", side_effect=requests.ConnectionError("down")), \
                patch.object(Config, "_SUPPORTED_PARAMS_CACHE", {}) as cache:
            assert Config.get_model_supported_params("a/x") is None
            assert cache == {}
        assert "could not fetch OpenRouter model capabilities" in capsys.readouterr().out

    def test_merge_node_llm_settings_model(self):
        """A node 'model' override is merged alongside existing settings."""
        merged = Config.merge_node_llm_settings({"writer": {"effort": "high"}}, {"writer": {"model": "a/opus"}})
        assert merged == {"writer": {"effort": "high", "model": "a/opus"}}

    def test_merge_node_llm_settings_model_null_removes(self):
        """A null 'model' removes an existing override and keeps other settings."""
        merged = Config.merge_node_llm_settings({"writer": {"model": "a/opus", "effort": "high"}}, {"writer": {"model": None}})
        assert merged == {"writer": {"effort": "high"}}

    def test_merge_node_llm_settings_model_null_without_override_stores_empty(self):
        """A null 'model' with no prior override stores an empty node entry."""
        assert Config.merge_node_llm_settings({}, {"seo": {"model": None}}) == {"seo": {}}

    def test_get_llm_uses_node_model(self):
        """get_llm() uses the node's model override, else the default model, for model and capability lookup."""
        with patch("langchain_openrouter.ChatOpenRouter") as mock_chat, \
                patch.object(Config, "OPENROUTER_MODEL", "a/default"), \
                patch.object(Config, "NODE_LLM_SETTINGS", {"writer": {"model": "a/opus"}}), \
                patch.object(Config, "get_model_supported_params", return_value=None) as caps:
            Config.get_llm("writer")
            assert mock_chat.call_args.kwargs["model"] == "a/opus"
            caps.assert_called_with("a/opus")
            Config.get_llm("seo")
            assert mock_chat.call_args.kwargs["model"] == "a/default"
            caps.assert_called_with("a/default")

    def test_get_llm_auto_routes_and_builds_chosen_model(self):
        """get_llm() routes an Auto step and builds the model the router chose."""
        from agentic.tools.model_router import RouteDecision
        auto = {"pool": POOL, "fallback": "a/small"}
        with patch.object(Config, "NODE_LLM_SETTINGS", {"writer": {"model": "auto", "auto": auto}}), \
                patch("agentic.tools.model_router.route",
                      return_value=RouteDecision("a/big", {}, 0.9, None)) as mock_route, \
                patch.object(Config, "get_model_supported_params", return_value={"reasoning"}) as caps, \
                patch("langchain_openrouter.ChatOpenRouter") as mock_chat:
            Config.get_llm("writer", routing_context={"topic": "t"})
        mock_route.assert_called_once_with("writer", auto, {"topic": "t"})
        caps.assert_called_with("a/big")
        assert mock_chat.call_args.kwargs["model"] == "a/big"

    def test_get_llm_auto_without_context_routes_with_empty_context(self):
        """get_llm() passes an empty context to the router when none is given."""
        from agentic.tools.model_router import RouteDecision
        auto = {"pool": POOL, "fallback": "a/small"}
        with patch.object(Config, "NODE_LLM_SETTINGS", {"writer": {"model": "auto", "auto": auto}}), \
                patch("agentic.tools.model_router.route",
                      return_value=RouteDecision("a/small", {}, None, "x")) as mock_route, \
                patch.object(Config, "get_model_supported_params", return_value=None), \
                patch("langchain_openrouter.ChatOpenRouter"):
            Config.get_llm("writer")
        mock_route.assert_called_once_with("writer", auto, {})

    @pytest.mark.parametrize("settings", [{"writer": {"model": "a/big"}}, {}])
    def test_get_llm_fixed_model_never_routes(self, settings):
        """get_llm() never invokes the router for a fixed or default model."""
        with patch.object(Config, "NODE_LLM_SETTINGS", settings), \
                patch("agentic.tools.model_router.route") as mock_route, \
                patch.object(Config, "get_model_supported_params", return_value=None), \
                patch("langchain_openrouter.ChatOpenRouter"):
            Config.get_llm("writer")
        mock_route.assert_not_called()

    @pytest.mark.parametrize("params, overrides, expected", [
        ({"reasoning", "temperature"}, {"model": "a/opus"}, "[writer] model: a/opus (effort: high)"),
        ({"temperature"}, {}, "[writer] model: a/default (temperature: 0.7)"),
        (set(), {}, "[writer] model: a/default (model defaults)"),
    ])
    def test_get_llm_logs_model_and_sent_setting(self, capsys, params, overrides, expected):
        """get_llm() prints the node's model and the effort/temperature actually sent."""
        with patch("langchain_openrouter.ChatOpenRouter"), \
                patch.object(Config, "OPENROUTER_MODEL", "a/default"), \
                patch.object(Config, "NODE_LLM_SETTINGS", {"writer": overrides}), \
                patch.object(Config, "get_model_supported_params", return_value=params):
            Config.get_llm("writer")
        assert capsys.readouterr().out.strip() == expected

    def test_get_node_llm_settings_model_only_when_overridden(self):
        """Resolved node settings include 'model' only for nodes that override it."""
        merged = Config.get_node_llm_settings({"writer": {"model": "a/opus"}})
        assert merged["writer"]["model"] == "a/opus"
        assert "model" not in merged["seo"]

    def test_get_llm_info_lists_node_models(self):
        """get_llm_info() reports per-node model overrides only."""
        with patch.object(Config, "OPENROUTER_MODEL", "a/default"), \
                patch.object(Config, "NODE_LLM_SETTINGS", {"writer": {"model": "a/opus"}, "seo": {"effort": "off"}}):
            info = Config.get_llm_info()
        assert info["primary"]["model"] == "a/default"
        assert info["node_models"] == {"writer": "a/opus"}

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
        {"writer": {"model": ""}},
        {"writer": {"model": 5}},
        {"writer": {"model": "   "}},
    ])
    def test_merge_node_llm_settings_rejects_invalid(self, updates):
        """Invalid nodes, keys, and values raise ValueError."""
        with pytest.raises(ValueError):
            Config.merge_node_llm_settings({}, updates)

    def test_get_model_pricing_per_million(self):
        """Pricing is USD per million tokens; one fetch fills both caches."""
        fake = MagicMock()
        fake.json.return_value = {"data": [
            {"id": "a/m", "supported_parameters": [], "pricing": {"prompt": "0.000003", "completion": "0.000015"}},
            {"id": "a/free", "supported_parameters": []},
        ]}
        with patch("requests.get", return_value=fake) as mock_get, \
                patch.object(Config, "_SUPPORTED_PARAMS_CACHE", {}), \
                patch.object(Config, "_PRICING_CACHE", {}):
            assert Config.get_model_pricing("a/m") == pytest.approx((3.0, 15.0))
            assert Config.get_model_pricing("a/free") is None
            assert Config.get_model_pricing("a/missing") is None
            Config.get_model_supported_params("a/m")
            assert mock_get.call_count == 1  # one fetch fills both caches

    @pytest.mark.parametrize("key, expected", [(None, False), ("", False), ("k", True)])
    def test_jev_available_follows_key(self, monkeypatch, key, expected):
        """jev_available is true iff TYPESAFE_API_KEY is non-empty."""
        monkeypatch.setattr(Config, "TYPESAFE_API_KEY", key)
        assert Config.jev_available() is expected


POOL = [{"model": "a/small", "criteria": "Simple"}, {"model": "a/big", "criteria": "Hard"}]
AUTO = {"pool": POOL, "fallback": "a/small"}


class TestMergeAuto:
    """Tests for the per-step Auto (JEV) block in merge_node_llm_settings"""

    @pytest.fixture(autouse=True)
    def jev_key(self, monkeypatch):
        """Make JEV available unless a test overrides the key."""
        monkeypatch.setattr(Config, "TYPESAFE_API_KEY", "k")

    def test_merge_auto_accepts_valid_block(self):
        merged = Config.merge_node_llm_settings({}, {"writer": {"model": "auto", "auto": AUTO}})
        assert merged["writer"] == {"model": "auto", "auto": AUTO}

    def test_merge_auto_keeps_stored_block_when_only_model_sent(self):
        stored = {"writer": {"model": "auto", "auto": AUTO}}
        assert Config.merge_node_llm_settings(stored, {"writer": {"effort": "low"}})["writer"]["auto"] == AUTO

    def test_merge_auto_fixed_model_drops_auto(self):
        stored = {"writer": {"model": "auto", "auto": AUTO}}
        assert "auto" not in Config.merge_node_llm_settings(stored, {"writer": {"model": "a/big"}})["writer"]

    def test_merge_auto_null_drops_auto(self):
        stored = {"writer": {"model": "auto", "auto": AUTO}}
        assert Config.merge_node_llm_settings(stored, {"writer": {"model": None}})["writer"] == {}

    @pytest.mark.parametrize("update", [
        {"model": "auto"},
        {"model": "a/big", "auto": AUTO},
        {"model": "auto", "auto": {**AUTO, "pool": POOL[:1]}},
        {"model": "auto", "auto": {**AUTO, "pool": POOL * 3}},
        {"model": "auto", "auto": {**AUTO, "pool": [POOL[0], POOL[0]]}},
        {"model": "auto", "auto": {**AUTO, "pool": [POOL[0], {"model": "a/big", "criteria": " "}]}},
        {"model": "auto", "auto": {"pool": POOL}},
        {"model": "auto", "auto": {**AUTO, "min_confidence": 1.5}},
        {"model": "auto", "auto": {**AUTO, "min_confidence": True}},
        {"model": "auto", "auto": {**AUTO, "extra": 1}},
        {"model": "auto", "auto": {**AUTO, "pool": [POOL[0], {"model": "auto", "criteria": "x"}]}},
        {"model": "auto", "auto": {**AUTO, "fallback": "auto"}},
    ])
    def test_merge_auto_rejects_invalid(self, update):
        with pytest.raises(ValueError):
            Config.merge_node_llm_settings({}, {"writer": update})

    def test_merge_auto_rejected_without_key(self, monkeypatch):
        monkeypatch.setattr(Config, "TYPESAFE_API_KEY", None)
        with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
            Config.merge_node_llm_settings({}, {"writer": {"model": "auto", "auto": AUTO}})

    def test_merge_stored_auto_editable_without_key(self, monkeypatch):
        """Key removed after configuring: unrelated edits and switching away still save."""
        monkeypatch.setattr(Config, "TYPESAFE_API_KEY", None)
        stored = {"writer": {"model": "auto", "auto": AUTO}}
        assert Config.merge_node_llm_settings(stored, {"writer": {"effort": "low"}})["writer"]["auto"] == AUTO
        assert Config.merge_node_llm_settings(stored, {"writer": {"model": "a/big"}})["writer"] == {"model": "a/big"}
