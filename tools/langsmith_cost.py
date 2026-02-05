"""
LangSmith-based cost tracking for workflow runs
"""
import os
from typing import Optional, Dict, Any


def get_langsmith_run_cost(run_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cost information from LangSmith for a specific run

    Args:
        run_id: LangSmith run ID

    Returns:
        Dict with cost info or None if unavailable
    """
    try:
        from langsmith import Client

        # Check if LangSmith is configured
        api_key = os.getenv("LANGCHAIN_API_KEY")
        if not api_key:
            return None

        client = Client()
        run = client.read_run(run_id)

        # Extract token usage and cost
        total_tokens = run.total_tokens or 0
        prompt_tokens = run.prompt_tokens or 0
        completion_tokens = run.completion_tokens or 0

        # LangSmith may have cost calculated
        total_cost = getattr(run, "total_cost", None)

        # If cost not available, estimate based on tokens
        if total_cost is None and total_tokens > 0:
            # Estimate for Claude 3.5 Sonnet (default)
            # $3/1M input, $15/1M output
            input_cost = (prompt_tokens / 1_000_000) * 3.00
            output_cost = (completion_tokens / 1_000_000) * 15.00
            total_cost = input_cost + output_cost

        return {
            "run_id": run_id,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_cost_usd": total_cost,
            "run_url": f"https://smith.langchain.com/o/{run.project_id}/runs/{run_id}" if hasattr(run, "project_id") else None
        }

    except Exception as e:
        print(f"⚠️  Could not fetch LangSmith cost: {e}")
        return None


def format_langsmith_cost_report(cost_info: Dict[str, Any]) -> str:
    """
    Format cost report from LangSmith data

    Args:
        cost_info: Cost info dict from get_langsmith_run_cost

    Returns:
        Formatted cost report string
    """
    if not cost_info:
        return ""

    report = []
    report.append("\n" + "="*80)
    report.append("💰 COST REPORT (via LangSmith)")
    report.append("="*80)

    report.append(f"\n📊 Total Usage:")
    report.append(f"   Prompt tokens:     {cost_info['prompt_tokens']:,}")
    report.append(f"   Completion tokens: {cost_info['completion_tokens']:,}")
    report.append(f"   Total tokens:      {cost_info['total_tokens']:,}")

    if cost_info.get("total_cost_usd"):
        report.append(f"\n💵 Total Cost: ${cost_info['total_cost_usd']:.4f}")

    if cost_info.get("run_url"):
        report.append(f"\n🔗 View detailed trace: {cost_info['run_url']}")

    report.append("="*80)
    return "\n".join(report)
