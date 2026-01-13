"""Permission scope builder for tool governance."""

from typing import Any, Dict, List

from loguru import logger

from ..registry import tool_registry


def build_required_scopes(tool_name: str, arguments: Dict[str, Any]) -> List[str]:
    """
    Get required permission scopes for a tool operation.

    Fetches base scopes from tool registry metadata, then adds
    resource-specific scopes based on tool arguments (e.g., specific file paths).

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        List of required permission scopes
    """
    # Start with base scopes from registry
    tool_record = tool_registry.get_tool(tool_name)
    if tool_record and tool_record.required_scopes:
        base_scopes = tool_record.required_scopes.copy()
    else:
        # Fallback: generate basic scope if not in registry
        logger.warning(
            f"Tool {tool_name} not found in registry or has no required_scopes, "
            f"using fallback scope"
        )
        base_scopes = [f"tool:{tool_name}"]

    # Add resource-specific scopes based on arguments
    # These are dynamic and depend on actual operation context
    if tool_name in {"write_file", "delete_file", "read_file"}:
        path = arguments.get("path", "")
        if path:
            base_scopes.append(f"resource:path:{path}")

    elif tool_name == "move_file":
        source = arguments.get("source", "")
        dest = arguments.get("destination", "")
        if source:
            base_scopes.append(f"resource:path:{source}")
        if dest:
            base_scopes.append(f"resource:path:{dest}")

    elif tool_name == "execute_command":
        command = arguments.get("command", "")
        if command:
            # Add specific command being executed (first 50 chars)
            cmd_preview = command[:50] if len(command) > 50 else command
            base_scopes.append(f"resource:command:{cmd_preview}")

    elif tool_name in {"create_directory", "list_directory"}:
        path = arguments.get("path", "")
        if path:
            base_scopes.append(f"resource:path:{path}")

    return base_scopes
