"""Integration tests for failure mode handling (Gap 9)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError
from redis import asyncio as aioredis

from src.meta_mcp.governance.approval import (
    ApprovalDecision,
    ApprovalProvider,
    ApprovalResponse,
)
from src.meta_mcp.leases import lease_manager
from src.meta_mcp.middleware import GovernanceMiddleware
from src.meta_mcp.state import governance_state
from src.meta_mcp.supervisor import get_tool_schema
from tests.conftest import read_audit_log

pytestmark = [pytest.mark.integration]


@pytest.mark.asyncio
async def test_redis_failure_during_lease_validation_fails_closed(mock_fastmcp_context):
    """Redis failures during lease validation should fail closed."""
    mock_fastmcp_context.request_context.tool_name = "read_file"
    mock_fastmcp_context.request_context.session_id = "redis-fail-session"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt"}

    call_next = AsyncMock()
    middleware = GovernanceMiddleware()

    with patch.object(
        lease_manager, "_get_redis", side_effect=aioredis.ConnectionError("Redis down")
    ):
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(mock_fastmcp_context, call_next)

    assert "No valid lease" in str(exc_info.value)
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_governance_state_timeout_requires_approval(mock_fastmcp_context):
    """Governance mode timeouts should require approval and avoid exposure."""
    with patch.object(
        governance_state, "_get_redis", side_effect=aioredis.TimeoutError("Redis timeout")
    ), patch("src.meta_mcp.supervisor._expose_tool", AsyncMock()) as expose_tool:
        with pytest.raises(ToolError) as exc_info:
            await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)

    assert "requires approval" in str(exc_info.value)
    expose_tool.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_elicitation_timeout_denies_and_audits(
    governance_in_permission,
    grant_lease,
    audit_log_path,
    mock_fastmcp_context,
):
    """Elicitation timeout should deny execution and write audit entry."""

    class TimeoutProvider(ApprovalProvider):
        async def request_approval(self, request):
            return ApprovalResponse(
                request_id=request.request_id,
                decision=ApprovalDecision.TIMEOUT,
                selected_scopes=[],
            )

        async def is_available(self) -> bool:
            return True

        def get_name(self) -> str:
            return "Timeout Provider"

    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"

    await grant_lease(client_id="session-123", tool_name="write_file")

    middleware = GovernanceMiddleware()
    call_next = AsyncMock()

    provider = TimeoutProvider()
    with patch(
        "src.meta_mcp.middleware.get_approval_provider",
        AsyncMock(return_value=provider),
    ):
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(mock_fastmcp_context, call_next)

    assert "denied" in str(exc_info.value).lower()
    call_next.assert_not_called()

    await asyncio.sleep(0.2)
    entries = read_audit_log(audit_log_path)
    timeout_entries = [
        entry
        for entry in entries
        if entry.get("event") == "approval_timeout"
        and entry.get("tool_name") == "write_file"
    ]
    assert timeout_entries


@pytest.mark.asyncio
async def test_empty_session_id_fails_closed(mock_fastmcp_context):
    """Empty session IDs should fail closed during lease validation."""
    mock_fastmcp_context.request_context.session_id = ""
    mock_fastmcp_context.request_context.tool_name = "read_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt"}

    call_next = AsyncMock()
    middleware = GovernanceMiddleware()

    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    assert "No valid lease" in str(exc_info.value)
    call_next.assert_not_called()
