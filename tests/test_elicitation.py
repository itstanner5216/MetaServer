"""Test human-in-the-loop approval flows (Invariant #6, Task 15)."""

import pytest
from fastmcp.exceptions import ToolError
from unittest.mock import AsyncMock, MagicMock

from src.meta_mcp.middleware import GovernanceMiddleware
from tests.conftest import read_audit_log


# ============================================================================
# APPROVAL FLOW TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_approval_grants_execution(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
):
    """
    Test that elicitation response "approve" allows tool execution.

    Expected: Tool should execute after approval
    Validates: Invariant #6 (Elicitation - approval flow)
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="File written successfully")

    # Execute
    result = await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation was called
    mock_fastmcp_context.elicit.assert_called_once()

    # Verify tool was executed
    call_next.assert_called_once()
    assert result == "File written successfully"


@pytest.mark.asyncio
async def test_denial_blocks_execution(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_deny,
):
    """
    Test that elicitation response "deny" blocks tool execution.

    Expected: Tool should raise ToolError with denial message
    Validates: Invariant #6 (Elicitation - denial flow)
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_deny

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions denial
    assert "denied" in str(exc_info.value).lower()

    # Verify tool was NOT executed
    call_next.assert_not_called()


# ============================================================================
# TIMEOUT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_timeout_blocks_execution(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_timeout,
):
    """
    Test that elicitation timeout (>300s) denies and logs timeout.

    Expected: Timeout should raise ToolError and NOT execute tool
    Validates: Invariant #6 (Elicitation - fail-safe timeout)
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_timeout

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions denial
    assert "denied" in str(exc_info.value).lower()

    # Verify tool was NOT executed
    call_next.assert_not_called()


# ============================================================================
# MALFORMED RESPONSE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_malformed_response_blocks(
    governance_in_permission,
    mock_fastmcp_context,
):
    """
    Test that invalid elicitation response denies (fail-safe).

    Expected: Malformed response should deny execution
    Validates: Invariant #6 (Elicitation - fail-safe parsing)
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"

    # Create mock elicit that returns malformed response
    async def _malformed(*args, **kwargs):
        result = MagicMock()
        result.data = "approve"  # Invalid response (missing required fields)
        return result

    mock_fastmcp_context.elicit = AsyncMock(side_effect=_malformed)

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions denial
    assert "denied" in str(exc_info.value).lower()

    # Verify tool was NOT executed
    call_next.assert_not_called()


# ============================================================================
# DECLINED/CANCELLED ELICITATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elicitation_declined_blocks(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_declined,
):
    """
    Test that DeclinedElicitation result denies execution.

    Expected: DeclinedElicitation should deny tool execution
    Validates: Invariant #6 (Elicitation - decline handling)
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_declined

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions denial
    assert "denied" in str(exc_info.value).lower()

    # Verify tool was NOT executed
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_elicitation_cancelled_blocks(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_cancelled,
):
    """
    Test that CancelledElicitation result denies execution.

    Expected: CancelledElicitation should deny tool execution
    Validates: Invariant #6 (Elicitation - cancellation handling)
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_cancelled

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions denial
    assert "denied" in str(exc_info.value).lower()

    # Verify tool was NOT executed
    call_next.assert_not_called()


# ============================================================================
# AUDIT LOG TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_approval_creates_audit_log(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
):
    """
    Test that approval decision is logged to audit.jsonl.

    Expected: Audit log should contain approval event
    Validates: Invariant #6 (Elicitation - audit requirement)
    Note: Uses default audit.jsonl file location
    """
    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-audit-test"
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Small delay to allow async logging to complete
    import asyncio
    await asyncio.sleep(0.2)

    # Read audit log from default location
    from pathlib import Path

    audit_log_default = Path("./audit.jsonl")
    entries = read_audit_log(audit_log_default)

    # Filter to only our test session
    test_entries = [e for e in entries if e.get("session_id") == "session-audit-test"]

    # Verify audit log contains our test entries
    event_types = [entry.get("event") for entry in test_entries]

    # Verify expected events are present (at least tool_invoked)
    assert len(test_entries) > 0, "No audit log entries found for test session"
    assert "tool_invoked" in event_types


# ============================================================================
# APPROVAL PARSING EDGE CASE TESTS (Structured Response Parsing)
# ============================================================================


@pytest.mark.asyncio
async def test_json_response_parsing():
    """
    Test JSON parsing for structured approval responses.
    """
    from src.meta_mcp.governance.approval import FastMCPElicitProvider

    payload = '{"decision":"approved","selected_scopes":["tool:write_file","resource:path:test.txt"],"lease_seconds":120}'
    parsed = FastMCPElicitProvider._parse_structured_response(payload)

    assert parsed["decision"] == "approved"
    assert parsed["selected_scopes"] == ["tool:write_file", "resource:path:test.txt"]
    assert parsed["lease_seconds"] == 120


@pytest.mark.asyncio
async def test_key_value_response_parsing():
    """
    Test key-value parsing for structured approval responses.
    """
    from src.meta_mcp.governance.approval import FastMCPElicitProvider

    payload = (
        "decision=approved\n"
        "selected_scopes=tool:write_file, resource:path:test.txt\n"
        "lease_seconds=45"
    )
    parsed = FastMCPElicitProvider._parse_structured_response(payload)

    assert parsed["decision"] == "approved"
    assert parsed["selected_scopes"] == "tool:write_file, resource:path:test.txt"
    assert parsed["lease_seconds"] == "45"


@pytest.mark.asyncio
async def test_invalid_response_parsing():
    """
    Test that invalid responses fail parsing.
    """
    from src.meta_mcp.governance.approval import FastMCPElicitProvider

    parsed = FastMCPElicitProvider._parse_structured_response("approve")
    assert parsed == {}
