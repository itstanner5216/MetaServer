"""Tests for middleware registry-driven sensitivity and scopes."""

from unittest.mock import AsyncMock

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.middleware import GovernanceMiddleware
from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry


@pytest.mark.asyncio
async def test_read_only_blocks_registry_sensitive_tool(
    governance_in_read_only, mock_fastmcp_context, lease_for_tool, monkeypatch
):
    """READ_ONLY mode should block tools marked sensitive in the registry."""
    registry = ToolRegistry()
    registry.add(
        ToolRecord(
            tool_id="custom_sensitive",
            server_id="custom",
            description_1line="Custom sensitive tool.",
            description_full="Custom sensitive tool that should be gated.",
            tags=["custom"],
            risk_level="sensitive",
            requires_permission=False,
            required_scopes=["tool:custom_sensitive"],
        )
    )

    monkeypatch.setattr("src.meta_mcp.middleware.tool_registry", registry)

    await lease_for_tool("custom_sensitive")

    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "custom_sensitive"
    mock_fastmcp_context.request_context.arguments = {}

    call_next = AsyncMock()

    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    assert "READ_ONLY" in str(exc_info.value)
    call_next.assert_not_called()


def test_required_scopes_include_yaml_scopes():
    """Required scopes should include registry-defined scopes from YAML."""
    scopes = GovernanceMiddleware._get_required_scopes(
        "write_file", {"path": "example.txt"}
    )

    assert "tool:write_file" in scopes
    assert "filesystem:write" in scopes
    assert "resource:path:example.txt" in scopes
