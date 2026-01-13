"""Test TTL-based scoped elevation cache (Invariant #6)."""

import asyncio

import pytest
from unittest.mock import AsyncMock

from src.meta_mcp.middleware import GovernanceMiddleware
from src.meta_mcp.state import governance_state


# ============================================================================
# ELEVATION GRANT AND AUTO-APPROVAL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_grants_on_approval(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    redis_client,
    lease_for_tool,
):
    """
    Test that approving a tool creates elevation key in Redis.

    Expected: After approval, elevation key should exist in Redis
    Validates: Invariant #6 (Scoped Elevation)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute (should grant elevation)
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Compute expected elevation hash
    elevation_hash = governance_state.compute_elevation_hash(
        tool_name="write_file", context_key="test.txt", session_id="session-123"
    )

    # Verify elevation exists in Redis
    exists = await governance_state.check_elevation(elevation_hash)
    assert exists is True


@pytest.mark.asyncio
async def test_elevation_auto_approves_same_path(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    granted_elevation,
    lease_for_tool,
):
    """
    Test that second call to same path skips elicitation.

    Expected: Second write_file to same path should not call elicit()
    Validates: Invariant #6 (Scoped Elevation - efficiency)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup: Pre-grant elevation
    await granted_elevation(
        tool_name="write_file", context_key="test.txt", session_id="session-123"
    )

    # Setup middleware and context
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = AsyncMock()  # Should NOT be called

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation was NOT triggered (elevation was used)
    mock_fastmcp_context.elicit.assert_not_called()

    # Verify tool was executed
    call_next.assert_called_once()


@pytest.mark.asyncio
async def test_elevation_requires_new_approval_different_path(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    granted_elevation,
    lease_for_tool,
):
    """
    Test that write_file to different path requires new approval.

    Expected: Elevation for test.txt should not apply to other.txt
    Validates: Invariant #6 (Scoped Elevation - security boundary)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup: Grant elevation for test.txt
    await granted_elevation(
        tool_name="write_file", context_key="test.txt", session_id="session-123"
    )

    # Setup middleware and context for OTHER path
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {
        "path": "other.txt",  # Different path
        "content": "data",
    }
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation WAS triggered (no elevation for other.txt)
    mock_fastmcp_context.elicit.assert_called_once()


# ============================================================================
# ELEVATION EXPIRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_expires_after_ttl(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    granted_elevation,
    lease_for_tool,
):
    """
    Test that elevation expires after TTL.

    Expected: After TTL expires, elicitation should be required again
    Validates: Invariant #6 (Scoped Elevation - TTL enforcement)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup: Grant elevation with 1-second TTL
    await granted_elevation(
        tool_name="write_file",
        context_key="test.txt",
        session_id="session-123",
        ttl=1,  # 1 second
    )

    # Wait for TTL to expire
    await asyncio.sleep(1.5)

    # Setup middleware and context
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-123"
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation WAS triggered (elevation expired)
    mock_fastmcp_context.elicit.assert_called_once()


# ============================================================================
# ELEVATION SESSION SCOPING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_scoped_to_session(
    governance_in_permission,
    mock_fastmcp_context,
    mock_elicit_approve,
    granted_elevation,
    lease_for_tool,
):
    """
    Test that elevation from one session does not apply to another.

    Expected: Elevation for session-A should not work for session-B
    Validates: Invariant #6 (Scoped Elevation - session isolation)
    """
    # Establish lease first (required by middleware)
    await lease_for_tool("write_file")

    # Setup: Grant elevation for session-A
    await granted_elevation(
        tool_name="write_file",
        context_key="test.txt",
        session_id="session-A",
    )

    # Setup middleware and context for session-B
    middleware = GovernanceMiddleware()
    mock_fastmcp_context.request_context.tool_name = "write_file"
    mock_fastmcp_context.request_context.arguments = {"path": "test.txt", "content": "data"}
    mock_fastmcp_context.request_context.session_id = "session-B"  # Different session
    mock_fastmcp_context.elicit = mock_elicit_approve

    # Create mock call_next
    call_next = AsyncMock(return_value="Success")

    # Execute
    await middleware.on_call_tool(mock_fastmcp_context, call_next)

    # Verify elicitation WAS triggered (different session)
    mock_fastmcp_context.elicit.assert_called_once()


# ============================================================================
# ELEVATION HASH COMPUTATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_hash_computation():
    """
    Test elevation hash computation format.

    Expected: Hash should be SHA256 with elevation: prefix
    Validates: Invariant #6 (Scoped Elevation - hash security)
    """
    # Compute hash
    hash_key = governance_state.compute_elevation_hash(
        tool_name="write_file",
        context_key="test.txt",
        session_id="session-123",
    )

    # Verify format
    assert hash_key.startswith("elevation:")
    assert len(hash_key) == len("elevation:") + 64  # SHA256 = 64 hex chars

    # Verify deterministic (same inputs = same hash)
    hash_key2 = governance_state.compute_elevation_hash(
        tool_name="write_file",
        context_key="test.txt",
        session_id="session-123",
    )
    assert hash_key == hash_key2

    # Verify different inputs = different hash
    hash_key3 = governance_state.compute_elevation_hash(
        tool_name="write_file",
        context_key="other.txt",  # Different context
        session_id="session-123",
    )
    assert hash_key != hash_key3


# ============================================================================
# ELEVATION MANDATORY TTL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_mandatory_ttl(redis_client):
    """
    Test that granting elevation with TTL=0 should fail.

    Expected: grant_elevation(ttl=0) should return False
    Validates: Invariant #6 (Scoped Elevation - no permanent elevations)
    """
    # Compute hash
    hash_key = governance_state.compute_elevation_hash(
        tool_name="write_file",
        context_key="test.txt",
        session_id="session-123",
    )

    # Attempt to grant with TTL=0
    result = await governance_state.grant_elevation(hash_key, ttl=0)

    # Verify grant failed
    assert result is False

    # Verify elevation does NOT exist in Redis
    exists = await governance_state.check_elevation(hash_key)
    assert exists is False
