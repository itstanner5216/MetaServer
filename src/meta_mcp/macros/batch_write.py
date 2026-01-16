"""
Batch write operations for tools.

Provides batch update capabilities with validation and rollback support.
"""

from typing import Any

from ..registry.registry import ToolRegistry


def batch_update_tools(
    registry: ToolRegistry,
    updates: dict[str, dict[str, Any]],
    atomic: bool = False,
    rollback_on_error: bool = False,
    check_permissions: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Update multiple tools in a single batch operation.

    Args:
        registry: Tool registry instance
        updates: Dictionary mapping tool_id -> update fields
        atomic: If True, all updates succeed or all fail
        rollback_on_error: If True, rollback on any error
        check_permissions: If True, check permissions for dangerous tools
        dry_run: If True, preview changes without applying

    Returns:
        Result dictionary with success status and details
    """
    if not updates:
        return {"success": True, "updated": 0}

    # Validate risk levels
    valid_risk_levels = {"safe", "sensitive", "dangerous"}

    errors = {}
    updated_count = 0
    original_values = {}

    # Dry run mode
    if dry_run:
        preview = []
        for tool_id, fields in updates.items():
            tool = registry.get(tool_id)
            if tool:
                preview.append(
                    {
                        "tool_id": tool_id,
                        "current": {k: getattr(tool, k, None) for k in fields.keys()},
                        "proposed": fields,
                    }
                )
        return {"dry_run": True, "preview": preview}

    # Permission check for dangerous tools
    if check_permissions:
        for tool_id in updates:
            tool = registry.get(tool_id)
            if tool and tool.risk_level == "dangerous":
                return {
                    "success": False,
                    "error": f"Permission required to modify dangerous tool: {tool_id}",
                }

    # Perform updates
    for tool_id, fields in updates.items():
        tool = registry.get(tool_id)

        if tool is None:
            errors[tool_id] = "Tool not found"
            if atomic:
                break
            continue

        # Validate fields
        if "risk_level" in fields and fields["risk_level"] not in valid_risk_levels:
            errors[tool_id] = f"Invalid risk level: {fields['risk_level']}"
            if atomic or rollback_on_error:
                break
            continue

        # Store original values for rollback
        if atomic or rollback_on_error:
            original_values[tool_id] = {k: getattr(tool, k, None) for k in fields.keys()}

        # Apply updates
        try:
            for key, value in fields.items():
                setattr(tool, key, value)
            updated_count += 1
        except Exception as e:
            errors[tool_id] = str(e)
            if atomic or rollback_on_error:
                break

    # Rollback on error
    if (atomic or rollback_on_error) and errors:
        for tool_id, original_fields in original_values.items():
            tool = registry.get(tool_id)
            if tool:
                for key, value in original_fields.items():
                    setattr(tool, key, value)

        return {"success": False, "updated": 0, "errors": errors, "rolled_back": True}

    return {
        "success": len(errors) == 0,
        "updated": updated_count,
        "errors": errors if errors else None,
    }
