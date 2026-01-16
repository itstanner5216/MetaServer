"""Admin tools for MetaMCP governance control.

These tools ARE registered in the tool registry (config/tools.yaml) and follow
standard governance policy based on each tool's risk_level:
- get_governance_status is safe (allowed in READ_ONLY/PERMISSION/BYPASS)
- set_governance_mode is sensitive (approval in PERMISSION, blocked in READ_ONLY)
- revoke_all_elevations is dangerous (approval in PERMISSION, blocked in READ_ONLY)

Tools:
- set_governance_mode: Change execution mode
- get_governance_status: Query current mode and state
- revoke_all_elevations: Clear all scoped elevations
"""

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from loguru import logger

# Import governance components using package-safe absolute imports
# Note: Requires package installation via 'pip install -e .'
from meta_mcp.audit import AuditEvent, audit_logger
from meta_mcp.state import ExecutionMode, governance_state

# Create FastMCP server instance for admin tools
admin_server = FastMCP("AdminTools")


@admin_server.tool()
async def set_governance_mode(mode: str) -> str:
    """
    Set the global governance mode.

    ADMIN TOOL: This tool controls the governance system itself.
    Always requires approval in PERMISSION mode.

    Args:
        mode: Governance mode to set (read_only, permission, bypass)

    Returns:
        Confirmation message with old and new modes

    Raises:
        ToolError: If mode is invalid or Redis update fails
    """
    # Validate mode is a valid ExecutionMode
    try:
        new_mode = ExecutionMode(mode.lower())
    except ValueError:
        valid_modes = [m.value for m in ExecutionMode]
        raise ToolError(f"Invalid mode '{mode}'. Valid modes: {', '.join(valid_modes)}")

    # Get current mode for audit trail
    try:
        old_mode = await governance_state.get_mode()
    except Exception as e:
        logger.error(f"Failed to get current governance mode: {e}")
        raise ToolError(f"Failed to get current mode: {e}")

    # Don't change if already in requested mode
    if old_mode == new_mode:
        return f"Governance mode is already set to '{new_mode.value}'"

    # Set new mode
    try:
        success = await governance_state.set_mode(new_mode)
        if not success:
            raise ToolError("Failed to set governance mode in Redis")
    except Exception as e:
        logger.error(f"Failed to set governance mode: {e}")
        raise ToolError(f"Failed to set mode: {e}")

    # Audit the mode change
    audit_logger.log_mode_change(
        old_mode=old_mode.value,
        new_mode=new_mode.value,
        changed_by="admin_tool",
    )

    logger.warning(f"Governance mode changed: {old_mode.value} → {new_mode.value}")

    return (
        f"Governance mode changed successfully:\n"
        f"  Previous: {old_mode.value}\n"
        f"  Current:  {new_mode.value}\n\n"
        f"This change affects all subsequent tool invocations."
    )


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


@admin_server.tool()
async def revoke_all_elevations() -> str:
    """
    Revoke all active scoped elevations.

    This forces all subsequent sensitive operations to request new approval,
    even if they were previously elevated.

    ADMIN TOOL: Use with caution. This affects all sessions.

    Returns:
        Count of elevations revoked

    Raises:
        ToolError: If Redis operation fails
    """
    try:
        redis = await governance_state._get_redis()

        # Use SCAN to find all elevation keys (cursor-based iteration)
        elevation_keys = []
        cursor = 0

        while True:
            cursor, keys = await redis.scan(cursor=cursor, match="elevation:*", count=100)
            elevation_keys.extend(keys)

            # cursor == 0 means we've completed the iteration
            if cursor == 0:
                break

        # Delete all elevation keys
        if elevation_keys:
            deleted = await redis.delete(*elevation_keys)
            logger.warning(f"Revoked {deleted} elevation(s) via admin tool")

            # Audit the revocation
            audit_logger.log(
                AuditEvent.ELEVATIONS_REVOKED,
                action="revoke_all_elevations",
                count=deleted,
                changed_by="admin_tool",
            )

            return (
                f"Successfully revoked {deleted} active elevation(s).\n\n"
                f"All subsequent sensitive operations will require new approval."
            )
        logger.info("No active elevations to revoke")
        return "No active elevations found."

    except Exception as e:
        logger.error(f"Failed to revoke elevations: {e}")
        raise ToolError(f"Failed to revoke elevations: {e}")


# Export admin server for mounting
__all__ = ["admin_server"]
