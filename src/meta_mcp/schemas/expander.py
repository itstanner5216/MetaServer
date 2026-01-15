"""Schema expansion for progressive delivery.

This module restores full schemas from minimal forms by retrieving
the complete schema from the ToolRecord.schema_full field.

Design Plan Section: Phase 5 (Progressive Schemas)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def expand_schema(tool_id: str) -> dict[str, Any] | None:
    """
    Expand a minimal schema to its full form.

    Retrieves the full schema from ToolRecord.schema_full in the registry.
    This function is called by the expand_tool_schema meta-tool.

    Args:
        tool_id: Tool identifier to expand schema for

    Returns:
        Full schema with all descriptions, examples, defaults
        None if tool not found or schema not available

    Note:
        This function bypasses governance checks because the schema
        was already approved when the tool was initially leased via
        get_tool_schema(). Expansion is a read-only metadata operation.

    Example:
        minimal_schema = {"type": "object", "properties": {"path": {"type": "string"}}}
        full_schema = expand_schema("read_file")
        # Returns complete schema with descriptions, examples, etc.
    """
    # Import here to avoid circular dependency
    from ..registry import tool_registry

    # Get tool record from registry
    tool_record = tool_registry.get(tool_id)

    if not tool_record:
        logger.warning(f"Tool '{tool_id}' not found in registry")
        return None

    # Return full schema if available
    if tool_record.schema_full:
        logger.info(f"Expanded schema for '{tool_id}'")
        return tool_record.schema_full

    # Fallback: If schema_full not populated, return minimal schema
    # This maintains backward compatibility during Phase 5 rollout
    if tool_record.schema_min:
        logger.warning(f"Full schema not available for '{tool_id}', returning minimal schema")
        return tool_record.schema_min

    # No schema available
    logger.error(f"No schema available for '{tool_id}'")
    return None


def expand_schema_from_live_tool(tool_id: str, mcp_instance) -> dict[str, Any] | None:
    """
    Expand schema by retrieving from live MCP tool instance.

    This is a fallback method when ToolRecord.schema_full is not populated.
    It retrieves the schema directly from the FastMCP tool instance.

    Args:
        tool_id: Tool identifier to expand schema for
        mcp_instance: FastMCP instance to retrieve tool from

    Returns:
        Full schema from tool instance
        None if tool not found

    Note:
        This requires the tool to already be exposed in the MCP instance.
        Should only be used as fallback when schema_full is not available.
    """
    try:
        # This is an async operation, but we're in a sync context
        # Caller should use async version if needed
        import asyncio

        # Get tool from MCP instance
        if asyncio.iscoroutinefunction(mcp_instance.get_tool):
            # Need to await in async context
            logger.warning("expand_schema_from_live_tool called in sync context, use async version")
            return None

        tool = mcp_instance.get_tool(tool_id)

        if not tool:
            logger.warning(f"Tool '{tool_id}' not found in MCP instance")
            return None

        # Convert to MCP format and extract full schema
        mcp_tool = tool.to_mcp_tool()

        if mcp_tool.inputSchema:
            logger.info(f"Expanded schema for '{tool_id}' from live tool")
            return mcp_tool.inputSchema

        return None

    except Exception as e:
        logger.error(f"Failed to expand schema from live tool: {e}")
        return None


async def expand_schema_from_live_tool_async(
    tool_id: str, mcp_instance
) -> dict[str, Any] | None:
    """
    Async version of expand_schema_from_live_tool.

    Args:
        tool_id: Tool identifier to expand schema for
        mcp_instance: FastMCP instance to retrieve tool from

    Returns:
        Full schema from tool instance
        None if tool not found
    """
    try:
        # Get tool from MCP instance
        tool = await mcp_instance.get_tool(tool_id)

        if not tool:
            logger.warning(f"Tool '{tool_id}' not found in MCP instance")
            return None

        # Convert to MCP format and extract full schema
        mcp_tool = tool.to_mcp_tool()

        if mcp_tool.inputSchema:
            logger.info(f"Expanded schema for '{tool_id}' from live tool")
            return mcp_tool.inputSchema

        return None

    except Exception as e:
        logger.error(f"Failed to expand schema from live tool: {e}")
        return None
