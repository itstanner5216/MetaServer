"""Utilities for tool discovery formatting."""

from collections.abc import Iterable

from .registry.models import ToolCandidate, ToolRecord


def _format_tool_entry(tool: ToolCandidate | ToolRecord) -> list[str]:
    """Format a single tool as a compact multi-line entry for agent display.

    Returns a list of strings: tool name with sensitivity tag, description,
    and a blank separator line.
    """
    tool_id = tool.tool_id
    description = tool.description_1line
    sensitivity = "[SAFE]" if tool.risk_level == "safe" else "[SENSITIVE]"

    return [
        f"• {tool_id} {sensitivity}",
        f"  {description}",
        "",
    ]


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
        lines.extend(_format_tool_entry(tool))

    return "\n".join(lines).strip()
