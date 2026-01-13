"""Formatting helpers for tool registry search results."""

from collections.abc import Iterable

from .models import ToolCandidate, ToolRecord


def format_search_results(results: Iterable[ToolCandidate | ToolRecord]) -> str:
    """
    Format search results for agent consumption.

    Returns ONLY:
    - Tool name
    - One-sentence description
    - Sensitivity flag

    Does NOT include:
    - Arguments or schemas
    - Examples or usage hints
    - Recommendations or rankings

    Args:
        results: Iterable of ToolCandidate or ToolRecord objects

    Returns:
        Formatted string with minimal metadata
    """
    results_list = list(results)
    if not results_list:
        return "No tools found matching your query."

    lines = [f"Found {len(results_list)} tool(s):\n"]

    for tool in results_list:
        sensitivity = "[SAFE]" if tool.risk_level == "safe" else "[SENSITIVE]"
        tool_name = tool.tool_id
        description = tool.description_1line

        lines.append(f"• {tool_name} {sensitivity}")
        lines.append(f"  {description}")
        lines.append("")  # Blank line between tools

    return "\n".join(lines).strip()
