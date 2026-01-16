"""
Batch read operations for tools.

Provides efficient batch retrieval of multiple tools from the registry.
"""


from ..registry.models import ToolRecord
from ..registry.registry import ToolRegistry


def batch_read_tools(
    registry: ToolRegistry,
    tool_ids: list[str] | None,
    max_risk_level: str | None = None,
    max_batch_size: int = 1000,
    audit: bool = False,
    session_id: str | None = None,
    user_id: str | None = None,
    rate_limit: bool = False,
) -> dict[str, ToolRecord | None]:
    """
    Retrieve multiple tools in a single batch operation.

    Args:
        registry: Tool registry instance
        tool_ids: List of tool IDs to retrieve
        max_risk_level: Maximum risk level to allow (safe, sensitive, dangerous)
        max_batch_size: Maximum number of tools to retrieve
        audit: Whether to log this operation
        session_id: Session ID for audit/governance
        user_id: User ID for audit/governance
        rate_limit: Whether to apply rate limiting

    Returns:
        Dictionary mapping tool_id -> ToolRecord (or None if not found)
    """
    if tool_ids is None or len(tool_ids) == 0:
        return {}

    # Apply batch size limit
    if len(tool_ids) > max_batch_size:
        # Return error dict
        return {
            "error": f"Batch size {len(tool_ids)} exceeds maximum {max_batch_size}",
            **dict.fromkeys(tool_ids[:max_batch_size]),
        }

    # Define risk level hierarchy
    risk_hierarchy = {"safe": 0, "sensitive": 1, "dangerous": 2}

    max_risk = risk_hierarchy.get(max_risk_level, 2) if max_risk_level else 2

    # Retrieve tools
    results = {}
    for tool_id in tool_ids:
        tool = registry.get(tool_id)

        # Apply risk filter
        if tool is not None and max_risk_level:
            tool_risk = risk_hierarchy.get(tool.risk_level, 0)
            if tool_risk > max_risk:
                tool = None  # Filter out tools above max risk

        results[tool_id] = tool

    # Audit logging if requested
    if audit and session_id:
        try:
            from ..audit import AuditEvent, audit_logger

            audit_logger.log(
                event=AuditEvent.TOOL_INVOKED,
                operation="batch_read",
                tool_name="batch_read_tools",
                session_id=session_id,
                user_id=user_id or "unknown",
                metadata={
                    "tool_count": len(tool_ids),
                    "found_count": sum(1 for t in results.values() if t is not None),
                    "max_risk_level": max_risk_level,
                },
            )
            audit_logger.flush()
        except Exception:
            # Don't fail operation if audit logging fails
            pass

    return results
