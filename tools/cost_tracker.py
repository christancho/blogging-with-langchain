"""
Cost tracking utility for LLM token usage and cost calculation
"""
from typing import Dict, Any


# Pricing per 1M tokens (as of Feb 2026)
# Source: https://www.anthropic.com/pricing
MODEL_PRICING = {
    # Claude 3.5 Sonnet
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,   # $3.00 per 1M input tokens
        "output": 15.00  # $15.00 per 1M output tokens
    },
    "claude-3-5-sonnet-latest": {
        "input": 3.00,
        "output": 15.00
    },
    # Claude 3.5 Haiku
    "claude-3-5-haiku-20241022": {
        "input": 0.80,   # $0.80 per 1M input tokens
        "output": 4.00   # $4.00 per 1M output tokens
    },
    # Claude 3 Opus
    "claude-3-opus-20240229": {
        "input": 15.00,
        "output": 75.00
    },
    # OpenRouter models (approximate pricing)
    "openai/gpt-4o": {
        "input": 5.00,
        "output": 15.00
    },
    "openai/gpt-4-turbo": {
        "input": 10.00,
        "output": 30.00
    }
}


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = "claude-3-5-sonnet-20241022"
) -> float:
    """
    Calculate cost for LLM usage

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model identifier

    Returns:
        Cost in USD
    """
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-3-5-sonnet-20241022"])

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return input_cost + output_cost


def extract_usage_from_response(response) -> Dict[str, int]:
    """
    Extract token usage from LLM response

    Args:
        response: LLM response object

    Returns:
        Dict with input_tokens and output_tokens
    """
    usage = {
        "input_tokens": 0,
        "output_tokens": 0
    }

    # Try to extract from response metadata
    if hasattr(response, "response_metadata"):
        metadata = response.response_metadata
        if "usage" in metadata:
            usage_data = metadata["usage"]
            usage["input_tokens"] = usage_data.get("input_tokens", 0)
            usage["output_tokens"] = usage_data.get("output_tokens", 0)

    # Fallback: try alternative attribute names
    elif hasattr(response, "usage_metadata"):
        usage_data = response.usage_metadata
        usage["input_tokens"] = usage_data.get("input_tokens", 0)
        usage["output_tokens"] = usage_data.get("output_tokens", 0)

    return usage


def update_state_cost(
    state: Dict[str, Any],
    node_name: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "claude-3-5-sonnet-20241022"
) -> Dict[str, Any]:
    """
    Update state with cost information from a node

    Args:
        state: Current state dict
        node_name: Name of the node (e.g., "research", "writer")
        input_tokens: Input tokens used
        output_tokens: Output tokens used
        model: Model identifier

    Returns:
        State updates to merge
    """
    # Calculate cost for this call
    call_cost = calculate_cost(input_tokens, output_tokens, model)

    # Get current totals
    total_input = state.get("total_input_tokens", 0)
    total_output = state.get("total_output_tokens", 0)
    total_cost = state.get("total_cost_usd", 0.0)
    cost_breakdown = state.get("cost_breakdown", {})

    # Update breakdown for this node
    if node_name not in cost_breakdown:
        cost_breakdown[node_name] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "calls": 0
        }

    cost_breakdown[node_name]["input_tokens"] += input_tokens
    cost_breakdown[node_name]["output_tokens"] += output_tokens
    cost_breakdown[node_name]["cost_usd"] += call_cost
    cost_breakdown[node_name]["calls"] += 1

    # Return state updates
    return {
        "total_input_tokens": total_input + input_tokens,
        "total_output_tokens": total_output + output_tokens,
        "total_cost_usd": total_cost + call_cost,
        "cost_breakdown": cost_breakdown
    }


def format_cost_report(state: Dict[str, Any]) -> str:
    """
    Format a cost report from state

    Args:
        state: State dict with cost tracking

    Returns:
        Formatted cost report string
    """
    total_input = state.get("total_input_tokens", 0)
    total_output = state.get("total_output_tokens", 0)
    total_cost = state.get("total_cost_usd", 0.0)
    breakdown = state.get("cost_breakdown", {})

    report = []
    report.append("\n" + "="*80)
    report.append("💰 COST REPORT")
    report.append("="*80)

    # Overall totals
    report.append(f"\n📊 Total Usage:")
    report.append(f"   Input tokens:  {total_input:,}")
    report.append(f"   Output tokens: {total_output:,}")
    report.append(f"   Total tokens:  {total_input + total_output:,}")
    report.append(f"\n💵 Total Cost: ${total_cost:.4f}")

    # Per-node breakdown
    if breakdown:
        report.append(f"\n📈 Breakdown by Node:")
        for node_name, data in sorted(breakdown.items()):
            calls = data.get("calls", 0)
            cost = data.get("cost_usd", 0.0)
            input_tok = data.get("input_tokens", 0)
            output_tok = data.get("output_tokens", 0)
            report.append(f"\n   {node_name.upper()}:")
            report.append(f"      Calls:         {calls}")
            report.append(f"      Input tokens:  {input_tok:,}")
            report.append(f"      Output tokens: {output_tok:,}")
            report.append(f"      Cost:          ${cost:.4f}")

    report.append("="*80)
    return "\n".join(report)
