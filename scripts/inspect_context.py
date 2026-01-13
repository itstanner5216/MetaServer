#!/usr/bin/env python3
"""
FastMCP Context Inspector

Purpose: Inspect the FastMCP Context object to identify the stable session/client
         identifier field for use in lease management and governance.

Usage: Run this script as a FastMCP tool to log all available context fields.

Security Note: This is a one-time investigation to resolve the client_id extraction
              issue identified in GAP_ANALYSIS_REPORT.md (Issue 1.1).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

# Create output directory
OUTPUT_DIR = Path(__file__).parent.parent / "workspace" / "context_inspection"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Create MCP server
mcp = FastMCP("Context Inspector")


@mcp.tool()
async def inspect_context(test_param: str = "test") -> str:
    """
    Inspects the FastMCP Context object and logs all available fields.

    Args:
        test_param: A test parameter to verify context across calls

    Returns:
        JSON string with all context fields and metadata
    """
    from fastmcp import Context

    # Get current context
    ctx = Context.get_current()

    # Extract all available attributes
    context_data = {
        "timestamp": datetime.now().isoformat(),
        "test_param": test_param,
        "context_type": str(type(ctx)),
        "available_attributes": {},
        "private_attributes": {},
        "methods": [],
    }

    # Inspect all attributes
    for attr_name in dir(ctx):
        try:
            # Skip magic methods
            if attr_name.startswith("__"):
                continue

            attr_value = getattr(ctx, attr_name)

            # Categorize by type
            if callable(attr_value):
                context_data["methods"].append(attr_name)
            elif attr_name.startswith("_"):
                # Private attributes
                context_data["private_attributes"][attr_name] = str(attr_value)
            else:
                # Public attributes - these are what we care about
                # Convert to string for JSON serialization
                if isinstance(attr_value, (str, int, float, bool, type(None))):
                    context_data["available_attributes"][attr_name] = attr_value
                else:
                    context_data["available_attributes"][attr_name] = str(attr_value)

        except Exception as e:
            context_data["available_attributes"][attr_name] = f"<Error: {e}>"

    # Look for common session/client ID patterns
    potential_ids = {}
    for attr_name, attr_value in context_data["available_attributes"].items():
        if any(keyword in attr_name.lower() for keyword in
               ["session", "client", "connection", "id", "user", "caller"]):
            potential_ids[attr_name] = attr_value

    context_data["potential_session_identifiers"] = potential_ids

    # Save to file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"context_inspection_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump(context_data, f, indent=2)

    # Also append to aggregate log
    log_file = OUTPUT_DIR / "context_inspection_log.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(context_data) + "\n")

    # Return summary
    summary = {
        "output_file": str(output_file),
        "total_attributes": len(context_data["available_attributes"]),
        "potential_session_identifiers": potential_ids,
        "recommendation": _analyze_identifiers(potential_ids),
    }

    return json.dumps(summary, indent=2)


def _analyze_identifiers(potential_ids: dict[str, Any]) -> str:
    """
    Analyzes potential session identifiers and provides recommendation.

    Args:
        potential_ids: Dictionary of potential identifier fields

    Returns:
        Recommendation string
    """
    if not potential_ids:
        return (
            "⚠️ WARNING: No obvious session/client identifier found. "
            "May need to implement custom ID generation. "
            "CRITICAL: Implement fail-closed behavior per GAP_ANALYSIS_REPORT.md"
        )

    # Priority order for ID field selection
    priority_fields = [
        "session_id",
        "client_id",
        "connection_id",
        "caller_id",
        "user_id",
    ]

    for field in priority_fields:
        if field in potential_ids:
            return (
                f"✅ RECOMMENDED: Use ctx.{field} = '{potential_ids[field]}'\n"
                f"This appears to be the most stable session identifier.\n"
                f"Next steps:\n"
                f"1. Test stability across multiple requests\n"
                f"2. Test stability across reconnections\n"
                f"3. Update supervisor.py and middleware.py\n"
                f"4. Document in security boundary"
            )

    # Fallback to first available
    first_field = list(potential_ids.keys())[0]
    return (
        f"⚠️ CAUTION: Best guess is ctx.{first_field} = '{potential_ids[first_field]}'\n"
        f"However, this may not be stable. Please verify:\n"
        f"1. Call this tool multiple times and check if value stays same\n"
        f"2. Reconnect and check if value changes\n"
        f"3. Consider implementing custom session tracking if unstable"
    )


@mcp.tool()
async def test_context_stability(call_number: int = 1) -> str:
    """
    Test if context fields remain stable across multiple calls.
    Call this tool 3-5 times with different call_numbers to verify stability.

    Args:
        call_number: Which test call this is (1, 2, 3, etc.)

    Returns:
        Comparison with previous calls
    """
    from fastmcp import Context

    ctx = Context.get_current()

    # Get potential ID fields
    potential_ids = {}
    for attr_name in dir(ctx):
        if (not attr_name.startswith("_") and
            any(kw in attr_name.lower() for kw in ["session", "client", "connection", "id"])):
            try:
                potential_ids[attr_name] = getattr(ctx, attr_name)
            except:
                pass

    # Load previous calls
    stability_file = OUTPUT_DIR / "stability_test.json"
    if stability_file.exists():
        with open(stability_file) as f:
            history = json.load(f)
    else:
        history = {"calls": []}

    # Add this call
    call_data = {
        "call_number": call_number,
        "timestamp": datetime.now().isoformat(),
        "identifiers": potential_ids,
    }
    history["calls"].append(call_data)

    # Save
    with open(stability_file, "w") as f:
        json.dump(history, f, indent=2)

    # Analyze stability
    if len(history["calls"]) == 1:
        return (
            f"Call #{call_number} recorded. Call this tool 2-3 more times "
            f"with different call_numbers to test stability."
        )

    # Compare with first call
    first_call = history["calls"][0]
    current_call = call_data

    stable_fields = []
    unstable_fields = []

    for field in first_call["identifiers"]:
        if field in current_call["identifiers"]:
            if first_call["identifiers"][field] == current_call["identifiers"][field]:
                stable_fields.append(field)
            else:
                unstable_fields.append(field)

    result = {
        "total_calls": len(history["calls"]),
        "stable_fields": stable_fields,
        "unstable_fields": unstable_fields,
        "verdict": "",
    }

    if stable_fields and not unstable_fields:
        result["verdict"] = (
            f"✅ STABLE: {', '.join(stable_fields)} remained constant across "
            f"{len(history['calls'])} calls. Recommend using: ctx.{stable_fields[0]}"
        )
    elif unstable_fields:
        result["verdict"] = (
            f"⚠️ UNSTABLE: {', '.join(unstable_fields)} changed between calls. "
            f"{'Use ' + stable_fields[0] + ' instead' if stable_fields else 'May need custom session tracking'}"
        )
    else:
        result["verdict"] = "❌ ERROR: No consistent fields found"

    return json.dumps(result, indent=2)


if __name__ == "__main__":
    print("FastMCP Context Inspector")
    print("=" * 50)
    print()
    print("This script creates two MCP tools:")
    print("  1. inspect_context - Logs all Context fields")
    print("  2. test_context_stability - Tests field stability")
    print()
    print("To use:")
    print("  1. Run: fastmcp dev scripts/inspect_context.py")
    print("  2. Call inspect_context tool from Claude Desktop")
    print("  3. Call test_context_stability 3-5 times")
    print("  4. Review output in workspace/context_inspection/")
    print()
    print("Output files:")
    print(f"  - {OUTPUT_DIR / 'context_inspection_*.json'}")
    print(f"  - {OUTPUT_DIR / 'stability_test.json'}")
    print()

    # Run the server
    mcp.run()
