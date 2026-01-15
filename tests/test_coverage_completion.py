"""Additional tests to achieve >90% coverage on middleware.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.middleware import GovernanceMiddleware

# ============================================================================
# CONTEXT KEY EXTRACTION TESTS (Lines 76-97)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_execute_command_context_key_truncation(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
):
    """
    Test that execute_command context key is truncated to 50 chars.

    Expected: Long commands should be truncated for context key
    Coverage: middleware.py lines 84-86
    """
    middleware = GovernanceMiddleware()

    # Setup with long command (>50 chars)
    long_command = "a" * 100
    mock_fastmcp_context.request_context.tool_name = "execute_command"
    mock_fastmcp_context.request_context.arguments = {"command": long_command}
    mock_fastmcp_context.request_context.session_id = "test-session"
    mock_fastmcp_context.elicit = mock_elicit_approve

    call_next = AsyncMock(return_value="Command executed")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify execution succeeded
    call_next.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_directory_operations_context_key(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
):
    """
    Test that directory operations use path as context key.

    Expected: create_directory, remove_directory use 'path' argument
    Coverage: middleware.py lines 76-77
    """
    middleware = GovernanceMiddleware()

    # Test create_directory
    mock_fastmcp_context.request_context.tool_name = "create_directory"
    mock_fastmcp_context.request_context.arguments = {"path": "/test/directory"}
    mock_fastmcp_context.request_context.session_id = "test-session"
    mock_fastmcp_context.elicit = mock_elicit_approve

    call_next = AsyncMock(return_value="Directory created")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify execution succeeded
    call_next.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_git_operations_context_key(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
):
    """
    Test that git operations use cwd as context key.

    Expected: git_commit, git_push use 'cwd' argument
    Coverage: middleware.py lines 89-90
    """
    middleware = GovernanceMiddleware()

    # Test git_commit
    mock_fastmcp_context.request_context.tool_name = "git_commit"
    mock_fastmcp_context.request_context.arguments = {"message": "test", "cwd": "/repo"}
    mock_fastmcp_context.request_context.session_id = "test-session"
    mock_fastmcp_context.elicit = mock_elicit_approve

    call_next = AsyncMock(return_value="Committed")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify execution succeeded
    call_next.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_admin_operations_context_key(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
):
    """
    Test that admin operations use tool name as context key.

    Expected: set_governance_mode, revoke_all_elevations use tool_name
    Coverage: middleware.py lines 93-94
    """
    middleware = GovernanceMiddleware()

    # Test set_governance_mode
    mock_fastmcp_context.request_context.tool_name = "set_governance_mode"
    mock_fastmcp_context.request_context.arguments = {"mode": "READ_ONLY"}
    mock_fastmcp_context.request_context.session_id = "test-session"
    mock_fastmcp_context.elicit = mock_elicit_approve

    call_next = AsyncMock(return_value="Mode changed")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify execution succeeded
    call_next.assert_called_once()


# ============================================================================
# APPROVAL REQUEST FORMATTING TESTS (Line 199)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_approval_request_long_argument_truncation(
    governance_in_permission,
    mock_fastmcp_context,
):
    """
    Test that approval request truncates arguments >200 chars.

    Expected: Long argument values should be truncated with "..."
    Coverage: middleware.py line 199
    """
    middleware = GovernanceMiddleware()

    # Setup with very long content argument (>200 chars)
    long_content = "x" * 300
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": long_content}
    mock_fastmcp_context.request_context.session_id = "test-session"

    # Mock elicit to capture the formatted request
    captured_request = None

    async def _capture_and_approve(request_message):
        nonlocal captured_request
        captured_request = request_message
        result = MagicMock()
        result.data = "approve"
        return result

    mock_fastmcp_context.elicit = AsyncMock(side_effect=_capture_and_approve)

    call_next = AsyncMock(return_value="Success")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify truncation occurred in request
    assert captured_request is not None
    assert "..." in captured_request  # Truncation marker present
    assert long_content not in captured_request  # Full content NOT present


# ============================================================================
# UNKNOWN MODE FAIL-SAFE TESTS (Lines 448-455)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_unknown_mode_fail_safe_denies(
    redis_client,
    mock_fastmcp_context,
):
    """
    Test that unknown governance mode fails safe to denial.

    Expected: Invalid mode should raise ToolError, NOT execute tool
    Coverage: middleware.py lines 448-455
    """
    middleware = GovernanceMiddleware()

    # Mock get_mode to return invalid mode (simulate corruption)
    from src.meta_mcp.state import governance_state

    # Create a mock invalid enum value
    class InvalidMode:
        value = "INVALID_MODE"

    with patch.object(governance_state, "get_mode", return_value=InvalidMode()):
        mock_fastmcp_context.request_context.tool_name = "write_file"
        mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
        mock_fastmcp_context.request_context.session_id = "test-session"

        call_next = AsyncMock()

        # Execute and verify ToolError is raised
        with pytest.raises(ToolError) as exc_info:
            await middleware.on_call_tool(mock_fastmcp_context, call_next)

        # Verify error message mentions unknown mode or denial
        error_message = str(exc_info.value).lower()
        assert "denied" in error_message or "unknown" in error_message

        # Verify tool was NOT executed (fail-safe)
        call_next.assert_not_called()
