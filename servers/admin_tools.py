"""Admin tools for MetaMCP governance visibility.

These tools are registered in the tool registry (config/tools.yaml) and follow
standard governance policy based on each tool's risk level:
- get_governance_status is safe (allowed in READ_ONLY/PERMISSION/BYPASS)

Tools:
- get_governance_status: Query current mode and state
"""

from fastmcp import FastMCP
from loguru import logger

# Import governance components using package-safe absolute imports
# Note: Requires package installation via 'pip install -e .'
from meta_mcp.middleware import SENSITIVE_TOOLS
from meta_mcp.registry import tool_registry
from meta_mcp.state import governance_state

# Create FastMCP server instance for admin tools
admin_server = FastMCP("AdminTools")


@admin_server.tool()
async def get_governance_status() -> str:
    """
    Get current governance system status.

    Returns information about:
    - Current governance mode
    - Active elevation count (if available)

    Returns:
        Formatted status report
    """
    # Get current mode
    try:
        mode = await governance_state.get_mode()
    except Exception as e:
        logger.error(f"Failed to get governance mode: {e}")
        return f"⚠️  Error getting governance status: {e}\nDefaulting to PERMISSION mode (fail-safe)"

    # Try to get elevation count (optional, best effort)
    elevation_count = "unknown"
    try:
        redis = await governance_state._get_redis()
        # Use SCAN to count elevation keys
        cursor = 0
        count = 0
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match="elevation:*", count=100)
            count += len(keys)
            if cursor == 0:
                break
        elevation_count = str(count)
    except Exception as e:
        logger.debug(f"Could not get elevation count: {e}")
        elevation_count = "unavailable"

    # Format status report
    sensitive_tool_ids = []
    try:
        sensitive_tool_ids = sorted(
            tool.tool_id
            for tool in tool_registry.get_all_summaries()
            if tool.risk_level in {"sensitive", "dangerous"}
        )
    except Exception as e:
        logger.debug(f"Could not load sensitive tool list from registry: {e}")

    if not sensitive_tool_ids:
        sensitive_tool_ids = sorted(SENSITIVE_TOOLS)

    sensitive_tools_display = ", ".join(sensitive_tool_ids)
    status_lines = [
        "# Governance System Status",
        "",
        f"**Mode:** `{mode.value}`",
        "",
        "**Mode Descriptions:**",
        "- `read_only`: All sensitive operations blocked",
        "- `permission`: Sensitive operations require approval",
        "- `bypass`: All operations allowed without approval",
        "",
        f"**Active Elevations:** {elevation_count}",
        "",
        f"**Sensitive Tools:** {sensitive_tools_display}",
    ]

    return "\n".join(status_lines)


__all__ = ["admin_server"]
