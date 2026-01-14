"""Test fail-safe defaults (Invariant #6, Task 16)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError
from redis import asyncio as aioredis

from src.meta_mcp.middleware import GovernanceMiddleware
from src.meta_mcp.state import ExecutionMode, governance_state

# ============================================================================
# REDIS FAILURE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_redis_down_defaults_to_permission():
    """
    Test that Redis connection failure returns PERMISSION mode.

    Expected: get_mode() should return PERMISSION when Redis is unavailable
    Validates: Invariant #6 (Fail-Safe - Redis failure handling)
    """
    # Mock Redis connection failure
    with patch.object(
        governance_state, "_get_redis", side_effect=aioredis.ConnectionError("Redis unavailable")
    ):
        # Get mode (should fail-safe to PERMISSION)
        mode = await governance_state.get_mode()

        # Verify mode is PERMISSION (fail-safe default)
        assert mode == ExecutionMode.PERMISSION


@pytest.mark.asyncio
async def test_redis_down_never_returns_bypass():
    """
    Test that Redis failure NEVER defaults to BYPASS mode.

    Expected: All Redis failures should return PERMISSION, never BYPASS
    Validates: Invariant #6 (Fail-Safe - security boundary)
    """
    # Test various Redis error scenarios
    redis_errors = [
        aioredis.ConnectionError("Connection refused"),
        aioredis.TimeoutError("Timeout"),
        Exception("Unexpected error"),
    ]

    for error in redis_errors:
        with patch.object(governance_state, "_get_redis", side_effect=error):
            # Get mode
            mode = await governance_state.get_mode()

            # Verify mode is PERMISSION (NEVER BYPASS)
            assert mode == ExecutionMode.PERMISSION
            assert mode != ExecutionMode.BYPASS


# ============================================================================
# ELICITATION ERROR TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elicitation_error_blocks(
    governance_in_permission,
    mock_fastmcp_context,
    lease_for_tool,
):
    """
    Test that exception during elicitation denies execution (fail-safe).

    Expected: Elicitation error should deny tool execution, not approve
    Validates: Invariant #6 (Fail-Safe - elicitation errors)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"

    # Create mock elicit that raises exception
    async def _error(*args, **kwargs):
        raise RuntimeError("Elicitation system failure")

    mock_fastmcp_context.elicit = AsyncMock(side_effect=_error)

    # Create mock call_next
    call_next = AsyncMock()

    # Execute and verify ToolError is raised (denied)
    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify error message mentions denial
    assert "denied" in str(exc_info.value).lower()

    # Verify tool was NOT executed (fail-safe)
    call_next.assert_not_called()


# ============================================================================
# INVALID MODE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_mode_defaults_to_permission(redis_client):
    """
    Test that invalid mode string in Redis returns PERMISSION.

    Expected: Invalid mode value should fail-safe to PERMISSION
    Validates: Invariant #6 (Fail-Safe - data validation)
    """
    # Set invalid mode string in Redis
    await redis_client.set("governance:mode", "invalid_mode_value")

    # Get mode (should fail-safe to PERMISSION)
    mode = await governance_state.get_mode()

    # Verify mode is PERMISSION (fail-safe default)
    assert mode == ExecutionMode.PERMISSION


# ============================================================================
# ELEVATION CHECK REDIS FAILURE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_check_redis_failure():
    """
    Test that Redis failure during elevation check returns False (no elevation).

    Expected: Elevation check should return False when Redis is unavailable
    Validates: Invariant #6 (Fail-Safe - elevation check failure)
    """
    # Compute elevation hash
    hash_key = governance_state.compute_elevation_hash(
        tool_name="write_file",
        context_key="test.txt",
        session_id="session-123",
    )

    # Mock Redis connection failure
    with patch.object(
        governance_state, "_get_redis", side_effect=aioredis.ConnectionError("Redis unavailable")
    ):
        # Check elevation (should fail-safe to False)
        has_elevation = await governance_state.check_elevation(hash_key)

        # Verify elevation check returns False (no elevation = require approval)
        assert has_elevation is False
