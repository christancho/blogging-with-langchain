"""Tests for the JEV model router used by Auto steps."""
from unittest.mock import MagicMock, patch

import pytest
from langchain_typesafe import ChoiceAnswer

from agentic.config import Config
from agentic.tools.model_router import (
    INSTRUCTIONS,
    NODE_JOBS,
    RouteDecision,
    build_state,
    route,
)

AUTO = {
    "pool": [
        {"model": "a/small", "criteria": "Simple"},
        {"model": "a/big", "criteria": "Hard"},
    ],
    "fallback": "a/small",
    "min_confidence": 0.6,
}


def _response(label, probs, confidence):
    """Build a fake ClassifierResponse holding one choice answer."""
    return MagicMock(
        choices={
            "model": ChoiceAnswer(
                type="choice", choice=label, probabilities=probs, confidence=confidence
            )
        }
    )


@pytest.fixture
def classifier_cls(monkeypatch):
    """Patch the classifier class and pricing; set an API key."""
    monkeypatch.setattr(Config, "TYPESAFE_API_KEY", "k")
    with patch("agentic.tools.model_router.TypeSafeClassifier") as cls, patch(
        "agentic.tools.model_router.Config.get_model_pricing", return_value=None
    ):
        cls.return_value.invoke.return_value = _response(
            "m2", {"m1": 0.2, "m2": 0.8}, 0.7
        )
        yield cls


def test_route_picks_top_choice(classifier_cls, capsys):
    d = route("writer", AUTO, {"topic": "x"})
    assert d == RouteDecision("a/big", {"a/small": 0.2, "a/big": 0.8}, 0.7, None)
    assert "JEV routing → a/big (p=0.80, confidence 0.70)" in capsys.readouterr().out


def test_route_low_confidence_falls_back(classifier_cls, capsys):
    classifier_cls.return_value.invoke.return_value = _response(
        "m2", {"m1": 0.2, "m2": 0.8}, 0.42
    )
    d = route("writer", AUTO, {})
    assert d.model == "a/small" and d.fallback_reason == "low confidence 0.42 < 0.6"
    assert d.probabilities == {"a/small": 0.2, "a/big": 0.8}
    out = capsys.readouterr().out
    assert "JEV routing fell back to a/small (low confidence 0.42 < 0.6)" in out
    assert "small 0.20 · big 0.80" in out


def test_route_default_min_confidence_is_0_6(classifier_cls):
    auto = {k: v for k, v in AUTO.items() if k != "min_confidence"}
    classifier_cls.return_value.invoke.return_value = _response(
        "m2", {"m1": 0.2, "m2": 0.8}, 0.59
    )
    d = route("writer", auto, {})
    assert d.model == "a/small" and d.fallback_reason == "low confidence 0.59 < 0.6"


def test_route_classifier_raises_falls_back(classifier_cls, capsys):
    classifier_cls.return_value.invoke.side_effect = RuntimeError("boom")
    d = route("writer", AUTO, {})
    assert d.model == "a/small" and d.fallback_reason.startswith("error: RuntimeError: boom")
    assert d.probabilities == {} and d.confidence is None
    out = capsys.readouterr().out
    assert "RuntimeError: boom" in out and "·" not in out


def test_route_classifier_construction_error_falls_back(classifier_cls):
    classifier_cls.side_effect = ValueError("bad key")
    d = route("writer", AUTO, {})
    assert d.model == "a/small" and d.fallback_reason.startswith("error: ValueError: bad key")


def test_route_without_key_falls_back(monkeypatch, capsys):
    monkeypatch.setattr(Config, "TYPESAFE_API_KEY", None)
    with patch("agentic.tools.model_router.TypeSafeClassifier") as cls:
        d = route("writer", AUTO, {})
        cls.assert_not_called()
    assert d.model == "a/small" and d.fallback_reason == "error: TYPESAFE_API_KEY not set"
    assert "TYPESAFE_API_KEY not set" in capsys.readouterr().out


def test_route_unknown_label_falls_back(classifier_cls):
    classifier_cls.return_value.invoke.return_value = _response(
        "m9", {"m1": 0.2, "m2": 0.8}, 0.9
    )
    d = route("writer", AUTO, {})
    assert d.model == "a/small" and d.fallback_reason == "error: unknown label 'm9'"


def test_route_option_text_includes_price(classifier_cls):
    pricing = {"a/big": (3.0, 15.0)}
    with patch(
        "agentic.tools.model_router.Config.get_model_pricing",
        side_effect=lambda m: pricing.get(m),
    ):
        route("writer", AUTO, {"topic": "x"})
    request = classifier_cls.return_value.invoke.call_args.args[0]
    choice = request["questions"]["model"]
    assert choice.criteria == {
        "m1": "a/small: Simple",
        "m2": "a/big: Hard (price: $3.00/M input, $15.00/M output tokens)",
    }
    assert choice.instructions == INSTRUCTIONS
    assert request["state"].startswith(NODE_JOBS["writer"])


def test_build_state_skips_none_and_stringifies():
    s = build_state(
        "seo", {"topic": "x", "article word count": 1200, "feedback": None, "long": "y" * 2000}
    )
    assert s.startswith(NODE_JOBS["seo"])
    assert "topic: x" in s and "article word count: 1200" in s and "feedback" not in s
    assert "long: " + "y" * 1500 + "\n" in s + "\n" and "y" * 1501 not in s


def test_node_jobs_cover_every_node():
    assert set(NODE_JOBS) == set(Config.NODE_LLM_DEFAULTS)


def test_route_missing_probability_prints_na(classifier_cls, capsys):
    classifier_cls.return_value.invoke.return_value = _response("m2", {"m1": 0.9}, 0.7)
    d = route("writer", AUTO, {})
    out = capsys.readouterr().out
    assert d.model == "a/big"
    assert "p=n/a" in out
    assert "p=0.00" not in out


def test_route_malformed_pool_entry_falls_back(classifier_cls):
    bad = {**AUTO, "pool": [{"model": "a/small", "criteria": "Simple"}, {"model": "a/big"}]}
    d = route("writer", bad, {})
    assert d.model == "a/small"
    assert d.fallback_reason.startswith("error: ")
