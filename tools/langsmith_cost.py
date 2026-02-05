"""
LangSmith-based cost tracking for workflow runs
"""
import os
from typing import Optional, Dict, Any


def get_latest_run_cost(project_name: str) -> Optional[Dict[str, Any]]:
    """
    Get cost information from the most recent run in a project

    Args:
        project_name: LangSmith project name

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

        # Get the most recent run from the project
        runs = list(client.list_runs(
            project_name=project_name,
            limit=1,
            execution_order=1  # Descending order (most recent first)
        ))

        if not runs:
            return None

        run = runs[0]
        return _extract_cost_from_run(run)

    except Exception as e:
        print(f"⚠️  Could not fetch LangSmith cost: {e}")
        return None


def _extract_cost_from_run(run) -> Dict[str, Any]:
    """
    Extract cost and token information from a LangSmith run object

    Args:
        run: LangSmith Run object

    Returns:
        Dict with cost info
    """
    # Extract token usage and cost
    total_tokens = getattr(run, "total_tokens", 0) or 0
    prompt_tokens = getattr(run, "prompt_tokens", 0) or 0
    completion_tokens = getattr(run, "completion_tokens", 0) or 0

    # LangSmith may have cost calculated
    total_cost = getattr(run, "total_cost", None)
    prompt_cost = getattr(run, "prompt_cost", None)
    completion_cost = getattr(run, "completion_cost", None)

    # If cost not available, estimate based on tokens (Claude 3.5 Sonnet default)
    if total_cost is None and total_tokens > 0:
        # $3/1M input, $15/1M output
        input_cost = (prompt_tokens / 1_000_000) * 3.00
        output_cost = (completion_tokens / 1_000_000) * 15.00
        total_cost = input_cost + output_cost
        prompt_cost = input_cost
        completion_cost = output_cost

    # Get run URL
    run_id = str(run.id)
    run_url = None
    if hasattr(run, "url") and run.url:
        run_url = run.url
    else:
        # Try to construct URL
        project_name = getattr(run, "session_name", None)
        if project_name:
            run_url = f"https://smith.langchain.com"

    return {
        "run_id": run_id,
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_cost_usd": total_cost,
        "prompt_cost_usd": prompt_cost,
        "completion_cost_usd": completion_cost,
        "run_url": run_url
    }


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
        return _extract_cost_from_run(run)

    except Exception as e:
        print(f"⚠️  Could not fetch LangSmith cost: {e}")
        return None


def format_langsmith_cost_report(cost_info: Dict[str, Any]) -> str:
    """
    Format cost report from LangSmith data

    Args:
        cost_info: Cost info dict from get_langsmith_run_cost or get_latest_run_cost

    Returns:
        Formatted cost report string
    """
    if not cost_info:
        return ""

    report = []
    report.append("\n" + "="*80)
    report.append("💰 COST REPORT (via LangSmith)")
    report.append("="*80)

    report.append(f"\n📊 Token Usage:")
    report.append(f"   Prompt tokens:     {cost_info['prompt_tokens']:,}")
    report.append(f"   Completion tokens: {cost_info['completion_tokens']:,}")
    report.append(f"   Total tokens:      {cost_info['total_tokens']:,}")

    if cost_info.get("total_cost_usd") is not None:
        total_cost = cost_info['total_cost_usd']
        prompt_cost = cost_info.get('prompt_cost_usd', 0)
        completion_cost = cost_info.get('completion_cost_usd', 0)

        report.append(f"\n💵 Cost Breakdown:")
        if prompt_cost:
            report.append(f"   Prompt cost:       ${prompt_cost:.4f}")
        if completion_cost:
            report.append(f"   Completion cost:   ${completion_cost:.4f}")
        report.append(f"   Total cost:        ${total_cost:.4f}")

    if cost_info.get("run_url"):
        report.append(f"\n🔗 View detailed trace: {cost_info['run_url']}")

    report.append("="*80)
    return "\n".join(report)
