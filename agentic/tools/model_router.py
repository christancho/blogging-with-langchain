"""
Model router for Auto (JEV) steps.

Asks TypeSafe's JEV classifier to pick the least costly model that can do a
pipeline step well, from a user-defined pool. Any failure falls back to the
configured fallback model so a job never stalls on routing.
"""
from dataclasses import dataclass

from langchain_typesafe import Choice, TypeSafeClassifier

from agentic.config import Config

DEFAULT_MIN_CONFIDENCE = 0.6

INSTRUCTIONS = "Choose the least costly model that can do this step well for this input."

NODE_JOBS: dict[str, str] = {
    "query_generator": "Generates 6 web search queries for researching a blog topic. Hard when the topic is niche, ambiguous, or very recent.",
    "content_synthesizer": "Reads fetched web sources and extracts key facts, quotes, and themes as JSON. Hard when sources are many, long, or contradictory.",
    "audience_analysis": "Describes the target audience for a blog topic. Hard when the topic spans several audiences or the instructions are specific.",
    "writer": "Writes or revises a long-form, well-sourced blog article from research. Hard for technical or niche topics and for revisions that must fix editor or fact-check feedback.",
    "fact_checker": "Extracts factual claims from a draft and judges each against web evidence. Hard for technical drafts with many precise claims.",
    "editor": "Reviews a draft for quality, structure, and cohesiveness and returns a JSON verdict. Hard for long or technical drafts.",
    "seo": "Writes SEO title, meta description, and keywords for a finished article. Usually simple.",
    "formatter": "Formats a finished article as Ghost-ready HTML. Usually simple and mechanical.",
}


@dataclass
class RouteDecision:
    """
    Outcome of routing one step.

    Attributes:
        model: Chosen model id (the fallback when routing failed or was unsure).
        probabilities: JEV probability per pool model id; {} on error.
        confidence: JEV confidence; None on error.
        fallback_reason: Why the fallback was used, or None if JEV's pick stands.
    """

    model: str
    probabilities: dict[str, float]
    confidence: float | None
    fallback_reason: str | None


def build_state(node: str, context: dict) -> str:
    """
    Build the classifier state text for a step.

    Args:
        node: Node name (key of NODE_JOBS).
        context: Input facts about this run; None values are skipped and
            others truncated to 1500 characters.

    Returns:
        The step's job description, a blank line, then one "key: value" line per item.
    """
    lines = [f"{k}: {str(v)[:1500]}" for k, v in context.items() if v is not None]
    return NODE_JOBS[node] + "\n\n" + "\n".join(lines)


def _option_text(model: str, criteria: str) -> str:
    """
    Build the option description sent to JEV for one pool model.

    Args:
        model: Model id.
        criteria: User-written description of when to pick it.

    Returns:
        "{model}: {criteria}" plus a price suffix when pricing is known.
    """
    text = f"{model}: {criteria}"
    pricing = Config.get_model_pricing(model)
    if pricing:
        text += f" (price: ${pricing[0]:.2f}/M input, ${pricing[1]:.2f}/M output tokens)"
    return text


def _fallback(node: str, fallback: str, reason: str, probs: dict, conf) -> RouteDecision:
    """
    Build and print a fallback decision.

    Args:
        node: Node name, used as the print prefix.
        fallback: Fallback model id.
        reason: Reason string stored on the decision.
        probs: Probabilities by model id ({} on error).
        conf: Confidence (None on error).

    Returns:
        RouteDecision for the fallback model.
    """
    if reason.startswith("error:"):
        print(f"[{node}] JEV routing failed, using {fallback} ({reason})")
    else:
        print(f"[{node}] JEV routing fell back to {fallback} ({reason})")
        _print_probs(probs)
    return RouteDecision(fallback, probs, conf, reason)


def _print_probs(probs: dict[str, float]) -> None:
    """
    Print the per-model probabilities line, using short names (text after the last '/').

    Args:
        probs: Probability by pool model id.
    """
    line = " · ".join(f"{m.rsplit('/', 1)[-1]} {p:.2f}" for m, p in probs.items())
    print(f"         {line}")


def route(node: str, auto_cfg: dict, context: dict) -> RouteDecision:
    """
    Pick a model for one step via the JEV classifier.

    Args:
        node: Node name (key of NODE_JOBS).
        auto_cfg: Stored auto block: {"pool": [{"model", "criteria"}, ...],
            "fallback": str, "min_confidence"?: float}.
        context: Input facts describing this run, passed to build_state.

    Returns:
        RouteDecision. Never raises: any classifier failure, unknown label, or
        confidence below the threshold yields the fallback model with a reason.
    """
    fallback = auto_cfg["fallback"]
    if not Config.jev_available():
        return _fallback(node, fallback, "error: TYPESAFE_API_KEY not set", {}, None)

    pool = auto_cfg["pool"]
    min_conf = auto_cfg.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
    labels = {f"m{i}": p["model"] for i, p in enumerate(pool, 1)}
    criteria = {f"m{i}": _option_text(p["model"], p["criteria"]) for i, p in enumerate(pool, 1)}

    try:
        classifier = TypeSafeClassifier(api_key=Config.TYPESAFE_API_KEY)
        response = classifier.invoke({
            "state": build_state(node, context),
            "questions": {"model": Choice(instructions=INSTRUCTIONS, criteria=criteria)},
        })
        answer = response.choices["model"]
        if answer.choice not in labels:
            raise LookupError(f"unknown label '{answer.choice}'")
        probs = {labels[k]: v for k, v in answer.probabilities.items() if k in labels}
        confidence = answer.confidence
        chosen = labels[answer.choice]
    except LookupError as e:
        return _fallback(node, fallback, f"error: {e}", {}, None)
    except Exception as e:  # any classifier failure must fall back, not stall the job
        return _fallback(node, fallback, f"error: {type(e).__name__}: {e}", {}, None)

    if confidence < min_conf:
        return _fallback(node, fallback, f"low confidence {confidence:.2f} < {min_conf}", probs, confidence)

    print(f"[{node}] JEV routing → {chosen} (p={probs.get(chosen, 0.0):.2f}, confidence {confidence:.2f})")
    _print_probs(probs)
    return RouteDecision(chosen, probs, confidence, None)
