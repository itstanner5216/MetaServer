"""Test tri-state governance mode enforcement (Invariant #4)."""

from unittest.mock import AsyncMock

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.middleware import GovernanceMiddleware

# ============================================================================
# READ_ONLY MODE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_read_only_blocks_sensitive_tools(
    governance_in_read_only, mock_fastmcp_context, lease_for_tool
):
    """
    Test that READ_ONLY mode blocks sensitive tool execution.

    Expected: write_file should raise ToolError with "READ_ONLY" message
    Validates: Invariant #4 (Tri-State Governance)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {
        "path": "test.txt",
        "content": "blocked",
    }

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions READ_ONLY
    assert "READ_ONLY" in str(exc_info.value)

    # Verify tool was NOT executed
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_read_only_allows_safe_tools(
    governance_in_read_only, mock_fastmcp_context, lease_for_tool
):
    """
    Test that READ_ONLY mode allows non-sensitive tools.

    Expected: read_file should execute without error
    Validates: Invariant #4 (Tri-State Governance)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("read_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "read_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt"}

    # Create mock call_next that returns success
    call_next = AsyncMock(return_value="file contents")

    # Execute
    result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify tool was executed
    call_next.assert_called_once()
    assert result == "file contents"


# ============================================================================
# BYPASS MODE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_bypass_allows_sensitive_tools(
    governance_in_bypass, mock_fastmcp_context, lease_for_tool
):
    """
    Test that BYPASS mode allows sensitive tool execution.

    Expected: write_file should execute without error
    Validates: Invariant #4 (Tri-State Governance)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {
        "path": "test.txt",
        "content": "allowed",
    }

    # Create mock call_next that returns success
    call_next = AsyncMock(return_value="File written successfully")

    # Execute
    result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify tool was executed
    call_next.assert_called_once()
    assert result == "File written successfully"


@pytest.mark.asyncio
async def test_bypass_logs_warning(governance_in_bypass, mock_fastmcp_context, lease_for_tool):
    """
    Test that BYPASS mode executes tools and does not block.

    Expected: Tool should execute without errors in BYPASS mode
    Validates: Invariant #4 (Tri-State Governance - BYPASS behavior)
    Note: Audit logging verified in test_approval_creates_audit_log
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {
        "path": "test.txt",
        "content": "allowed",
    }

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute - should not raise error
    result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify tool was executed
    call_next.assert_called_once()
    assert result == "Success"


# ============================================================================
# PERMISSION MODE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_permission_requires_approval(
    governance_in_permission, mock_fastmcp_context, mock_elicit_approve, lease_for_tool
):
    """
    Test that PERMISSION mode requires approval for sensitive tools.

    Expected: Elicitation should be triggered for write_file
    Validates: Invariant #4 (Tri-State Governance) + Invariant #6 (Elicitation)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {
        "path": "test.txt",
        "content": "needs approval",
    }
    mock_fastmcp_context.request_context.session_id = "test-session"

    # Assign mock elicit
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="File written")

    # Execute
    result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation was triggered
    mock_fastmcp_context.elicit.assert_called_once()

    # Verify tool was executed after approval
    call_next.assert_called_once()
    assert result == "File written"


@pytest.mark.asyncio
async def test_permission_allows_safe_tools(
    governance_in_permission, mock_fastmcp_context, lease_for_tool
):
    """
    Test that PERMISSION mode allows non-sensitive tools without approval.

    Expected: read_file should execute without elicitation
    Validates: Invariant #4 (Tri-State Governance - efficiency)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("read_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "read_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt"}

    # Create mock elicit (should NOT be called)
    mock_fastmcp_context.elicit = AsyncMock()

    # Create mock call_next
    call_next = AsyncMock(return_value="file contents")

    # Execute
    result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation was NOT triggered
    mock_fastmcp_context.elicit.assert_not_called()

    # Verify tool was executed
    call_next.assert_called_once()
    assert result == "file contents"
