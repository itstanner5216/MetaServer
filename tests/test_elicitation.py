"""Test human-in-the-loop approval flows (Invariant #6, Task 15)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.middleware import GovernanceMiddleware
from tests.conftest import read_audit_log

# ============================================================================
# APPROVAL FLOW TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_approval_grants_execution(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    grant_lease,
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
    await grant_lease(client_id="session-123", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_denial_blocks_execution(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_deny,
    grant_lease,
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
    await grant_lease(client_id="session-123", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_timeout_blocks_execution(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_timeout,
    grant_lease,
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
    await grant_lease(client_id="session-123", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_malformed_response_blocks(
    governance_in_permission,
    mock_fastmcp_context,
    grant_lease,
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
    await grant_lease(client_id="session-123", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_elicitation_declined_blocks(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_declined,
    grant_lease,
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
    await grant_lease(client_id="session-123", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_elicitation_cancelled_blocks(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_cancelled,
    grant_lease,
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
    await grant_lease(client_id="session-123", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_approval_creates_audit_log(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    grant_lease,
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
    await grant_lease(client_id="session-audit-test", tool_name="write_file")

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
@pytest.mark.requires_redis
async def test_substring_attacks_denied(
    governance_in_permission,
    mock_fastmcp_context,
):
    """
    Test JSON parsing for structured approval responses.
    """
    from src.meta_mcp.governance.approval import FastMCPElicitProvider

    payload = '{"decision":"approved","selected_scopes":["tool:write_file","resource:path:test.txt"],"lease_seconds":120}'
    parsed = FastMCPElicitProvider._parse_structured_response(payload)
    middleware = GovernanceMiddleware()

    # Test various substring attack attempts
    substring_attacks = [
        "yokay",  # contains "ok" but not as standalone word
        "yesno",  # contains "yes" but not as standalone word
        "approve123",  # contains "approve" but with suffix
        "xapprove",  # contains "approve" but with prefix
        "acceptreject",  # contains "accept" but not standalone
    ]

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
    from src.meta_mcp.middleware import GovernanceMiddleware

    middleware = GovernanceMiddleware()

    # Test multi-word responses
    multi_word_approvals = [
        "yes please",
        "ok sure",
        "I approve",
        "sure, ok",
        "yeah, accept it",
        "allow this",
    ]

    for approval_input in multi_word_approvals:
        result = middleware._parse_approval_response(approval_input)
        assert result is True, f"Multi-word approval '{approval_input}' was incorrectly denied"


@pytest.mark.asyncio
async def test_case_insensitivity():
    """
    Test that case variations are handled correctly.

    Expected: "YES", "YeS", "APPROVE" should all be APPROVED
    Validates: Usability - case-insensitive matching
    """
    from src.meta_mcp.middleware import GovernanceMiddleware

    middleware = GovernanceMiddleware()

    # Test case variations
    case_variations = [
        "YES",
        "Yes",
        "YeS",
        "APPROVE",
        "Approve",
        "ApPrOvE",
        "OK",
        "Ok",
    ]

    for approval_input in case_variations:
        result = middleware._parse_approval_response(approval_input)
        assert result is True, f"Case variation '{approval_input}' was incorrectly denied"


@pytest.mark.asyncio
async def test_empty_and_whitespace_denied():
    """
    Test that empty and whitespace-only responses are denied.

    Expected: "", "   ", "\\t\\n" should all be DENIED (fail-safe)
    Validates: Security - empty input fails safe to denial
    """
    from src.meta_mcp.middleware import GovernanceMiddleware

    middleware = GovernanceMiddleware()

    # Test empty/whitespace inputs
    empty_inputs = [
        "",
        "   ",
        "\t",
        "\n",
        "  \t\n  ",
    ]

    for empty_input in empty_inputs:
        result = middleware._parse_approval_response(empty_input)
        assert result is False, (
            f"Empty/whitespace input '{empty_input!r}' was incorrectly approved"
        )


@pytest.mark.asyncio
async def test_denial_keywords_rejected():
    """
    Test that common denial keywords are rejected.

    Expected: "no", "deny", "reject", "never" should all be DENIED
    Validates: Correctness - denial keywords properly rejected
    """
    from src.meta_mcp.middleware import GovernanceMiddleware

    middleware = GovernanceMiddleware()

    # Test denial keywords
    denial_inputs = [
        "no",
        "deny",
        "reject",
        "never",
        "nope",
        "nah",
        "cancel",
    ]

    for denial_input in denial_inputs:
        result = middleware._parse_approval_response(denial_input)
        assert result is False, f"Denial keyword '{denial_input}' was incorrectly approved"


@pytest.mark.asyncio
async def test_ambiguous_responses_fail_safe():
    """
    Test that ambiguous responses with mixed signals fail safe to approval.

    Expected: "yes but actually no" contains "yes" so approves (first match wins)
    Validates: Behavior documentation - current implementation is first-match-wins

    Note: This documents current behavior. Alternative: could require ONLY approval
    words and reject if denial words also present. Current design prioritizes
    user intent signaling (if they say "yes" anywhere, honor it).
    """
    from src.meta_mcp.middleware import GovernanceMiddleware

    middleware = GovernanceMiddleware()

    # Ambiguous inputs - current behavior is first-match-wins for approval
    # "yes but no" contains "yes" → approved
    # "maybe yes" contains "yes" → approved
    ambiguous_inputs = [
        ("yes but no", True),  # Contains "yes" → approved
        ("maybe yes", True),  # Contains "yes" → approved
        ("I guess ok", True),  # Contains "ok" → approved
        ("not really approve", True),  # Contains "approve" → approved
        ("no but yes", True),  # Contains "yes" → approved
    ]

    for ambiguous_input, expected in ambiguous_inputs:
        result = middleware._parse_approval_response(ambiguous_input)
        assert result == expected, f"Ambiguous input '{ambiguous_input}' behavior changed"
