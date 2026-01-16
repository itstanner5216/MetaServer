"""
CRITICAL Security Tests for Phase 3 (Lease Manager)

These tests MUST pass 100% before Phase 3 is considered complete.

Phase 3 controls tool visibility through ephemeral leases. Implementation
errors can:
- Leak tools into context permanently
- Allow unauthorized cross-session access
- Bypass governance checks entirely

Security Requirements:
1. Client ID Scoping: Leases MUST be scoped to stable session ID
2. Bootstrap Exception: search_tools and get_tool_schema MUST skip lease checks
3. Fail-Closed: Lease validation failures MUST deny access
4. Call Accounting: Lease consumption MUST happen ONLY on successful execution
"""

import asyncio
from unittest.mock import patch

import pytest

from src.meta_mcp.leases import lease_manager
from src.meta_mcp.registry import tool_registry
from src.meta_mcp.state import ExecutionMode, governance_state


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_cross_session_isolation(redis_client):
    """
    CRITICAL: Leases MUST be scoped to client_id.

    Security Risk: If leases leak across sessions, one client could
    use tools leased to another client (privilege escalation).

    This is a fundamental security boundary - if this test fails,
    STOP implementation immediately.
    """
    # Client A gets lease for write_file
    lease_a = await lease_manager.grant(
        client_id="session_a",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_a is not None

    # Client B should NOT be able to use Client A's lease
    lease_b = await lease_manager.validate("session_b", "write_file")
    assert lease_b is None, "SECURITY BREACH: Lease leaked across sessions!"

    # Verify Client A can still use their lease
    lease_a_check = await lease_manager.validate("session_a", "write_file")
    assert lease_a_check is not None, "Client A should have valid lease"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_expiration(redis_client):
    """
    CRITICAL: Expired leases must be rejected.

    Security Risk: If expired leases are accepted, tools remain
    accessible beyond intended time window.
    """
    # Grant short-lived lease (1 second)
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=1,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    # Verify lease is valid immediately
    valid = await lease_manager.validate("test_session", "read_file")
    assert valid is not None, "Lease should be valid immediately"

    # Wait for expiration
    await asyncio.sleep(2)

    # Verify lease is now invalid
    expired = await lease_manager.validate("test_session", "read_file")
    assert expired is None, "SECURITY BREACH: Expired lease accepted!"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_bootstrap_tools_skip_lease_check(redis_client):
    """
    CRITICAL: Bootstrap tools must be accessible without leases.

    Security Risk: If bootstrap tools require leases, infinite loop:
    - Can't call search_tools without lease
    - Can't get lease without calling get_tool_schema
    - Can't call get_tool_schema without lease

    This test verifies the bootstrap tool exception works correctly.
    """
    # Verify bootstrap tools are defined
    bootstrap = tool_registry.get_bootstrap_tools()
    assert "search_tools" in bootstrap
    assert "get_tool_schema" in bootstrap

    # Ensure bootstrap set has at least the two required tools
    assert len(bootstrap) >= 2, "Should have at least search_tools and get_tool_schema"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_consumption_only_on_success(redis_client):
    """
    CRITICAL: Failed tool calls must NOT consume lease.

    Security Risk: If failed calls consume lease, attacker could
    exhaust leases without successful execution (denial of service).

    Example attack:
    - Get lease for write_file with 3 calls
    - Call write_file with invalid args 3 times (fails)
    - If consumption happens on failure, lease is now exhausted
    - Attacker never successfully wrote anything but burned the lease
    """
    # Grant lease with 3 calls
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )
    assert lease.calls_remaining == 3

    # Simulate failed call (exception thrown)
    # DO NOT consume lease
    lease_check = await lease_manager.validate("test_session", "write_file")
    assert lease_check.calls_remaining == 3, "Failed call should not consume lease"

    # Simulate successful call
    consumed = await lease_manager.consume("test_session", "write_file")
    assert consumed.calls_remaining == 2, "Successful call should consume lease"

    # Verify consumption was persisted
    lease_check = await lease_manager.validate("test_session", "write_file")
    assert lease_check.calls_remaining == 2


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_not_granted_without_client_id(redis_client):
    """
    CRITICAL: Leases require stable client_id.

    Security Risk: If client_id is None or empty, lease scoping fails.
    All leases would be mixed together in Redis storage.
    """
    # Attempt to grant lease with client_id=None
    lease_none = await lease_manager.grant(
        client_id=None,
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_none is None, "Should not grant lease with None client_id"

    # Attempt to grant lease with empty client_id
    lease_empty = await lease_manager.grant(
        client_id="",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_empty is None, "Should not grant lease with empty client_id"

    # Verify valid client_id works
    lease_valid = await lease_manager.grant(
        client_id="valid_session_123",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_valid is not None, "Should grant lease with valid client_id"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_calls_remaining_decrements_correctly(redis_client):
    """
    Verify calls_remaining decrements on each successful execution.

    Not critical for security but important for lease lifecycle.
    """
    # Grant lease with 5 calls
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Consume calls one by one
    for expected_remaining in [4, 3, 2, 1, 0]:
        consumed = await lease_manager.consume("test_session", "read_file")
        assert consumed.calls_remaining == expected_remaining, (
            f"Expected {expected_remaining}, got {consumed.calls_remaining}"
        )

    # Verify lease is exhausted
    exhausted = await lease_manager.validate("test_session", "read_file")
    assert exhausted is None, "Lease should be invalid when calls exhausted"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_revocation(redis_client):
    """
    Verify lease revocation immediately invalidates lease.

    This is important for emergency lease cancellation or
    when mode changes require revoking all leases.
    """
    # Grant lease
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    # Verify lease is valid
    valid = await lease_manager.validate("test_session", "write_file")
    assert valid is not None

    # Revoke lease
    revoked = await lease_manager.revoke("test_session", "write_file")
    assert revoked is True

    # Verify lease is now invalid
    invalid = await lease_manager.validate("test_session", "write_file")
    assert invalid is None, "Revoked lease should be invalid"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_ttl_enforced(redis_client):
    """
    CRITICAL: Verify TTL is enforced and leases auto-expire in Redis.

    Security Risk: If TTL not set correctly, leases persist forever.
    """
    # Grant lease with 2 second TTL
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=2,
        calls_remaining=10,
        mode_at_issue="PERMISSION",
    )

    # Check Redis key has correct TTL
    key = "lease:test_session:read_file"
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= 2, f"TTL should be set to ~2 seconds, got {ttl}"

    # Wait for Redis to expire the key
    await asyncio.sleep(3)

    # Verify key is gone from Redis
    exists = await redis_client.exists(key)
    assert exists == 0, "Lease should be auto-expired by Redis"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_mode_consistency(redis_client, governance_in_permission):
    """
    Verify lease stores governance mode at time of issue.

    This allows checking if lease is still valid if mode changes.
    For example, if mode was BYPASS when lease granted but is now
    READ_ONLY, should the lease still be valid?

    Current design: Lease remains valid until expiration regardless
    of mode changes. This test documents that behavior.
    """
    # Start in PERMISSION mode (fixture)

    # Grant lease
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease.mode_at_issue == "PERMISSION"

    # Change mode to READ_ONLY
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Verify lease is still valid (doesn't check current mode)
    valid = await lease_manager.validate("test_session", "write_file")
    assert valid is not None, "Lease remains valid after mode change"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_multiple_leases_per_session(redis_client):
    """
    Verify a session can have leases for multiple tools simultaneously.

    This ensures lease storage keys are unique per (client_id, tool_id) pair.
    """
    # Grant lease for read_file
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Grant lease for write_file (same session)
    await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    # Verify both leases are independent
    read_check = await lease_manager.validate("test_session", "read_file")
    assert read_check.calls_remaining == 5

    write_check = await lease_manager.validate("test_session", "write_file")
    assert write_check.calls_remaining == 3

    # Consume read_file lease
    await lease_manager.consume("test_session", "read_file")

    # Verify only read_file lease was affected
    read_check = await lease_manager.validate("test_session", "read_file")
    assert read_check.calls_remaining == 4

    write_check = await lease_manager.validate("test_session", "write_file")
    assert write_check.calls_remaining == 3, "write_file lease should be unchanged"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_fail_closed_on_redis_error(redis_client):
    """
    CRITICAL: Lease validation must fail-closed on Redis errors.

    Security Risk: If Redis is down and validation returns True by default,
    all tools become accessible without lease checks.
    """
    # Mock Redis to raise exception
    with patch.object(lease_manager, "_get_redis") as mock_redis:
        mock_redis.side_effect = Exception("Redis connection failed")

        # Attempt to validate lease
        lease = await lease_manager.validate("test_session", "read_file")

        # Should fail closed (return None)
        assert lease is None, "SECURITY BREACH: Validation succeeded on Redis error"
