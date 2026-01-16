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
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from redis import asyncio as aioredis

from src.meta_mcp.leases import lease_manager
from src.meta_mcp.state import ExecutionMode, governance_state
from src.meta_mcp.supervisor import get_tool_schema, search_tools
from tests.test_utils import mock_fastmcp_context


pytestmark = pytest.mark.requires_redis


@pytest.mark.asyncio
async def test_cross_session_isolation(redis_client):
    """
    CRITICAL: Leases MUST be scoped to client_id.

    Security Risk: If leases leak across sessions, one client could
    use tools leased to another client (privilege escalation).
    """
    lease_a = await lease_manager.grant(
        client_id="session_a",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_a is not None

    lease_b = await lease_manager.validate("session_b", "write_file")
    assert lease_b is None, "SECURITY BREACH: Lease leaked across sessions!"

    lease_a_check = await lease_manager.validate("session_a", "write_file")
    assert lease_a_check is not None, "Client A should have valid lease"


@pytest.mark.asyncio
async def test_lease_expiration(redis_client):
    """
    CRITICAL: Expired leases must be rejected.

    Security Risk: If expired leases are accepted, tools remain
    accessible beyond intended time window.
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=1,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    valid = await lease_manager.validate("test_session", "read_file")
    assert valid is not None, "Lease should be valid immediately"

    await asyncio.sleep(1.5)

    expired = await lease_manager.validate("test_session", "read_file")
    assert expired is None, "SECURITY BREACH: Expired lease accepted!"


@pytest.mark.asyncio
async def test_bootstrap_tools_skip_lease_check(redis_client, governance_in_read_only):
    """
    CRITICAL: Bootstrap tools must be accessible without leases.

    Security Risk: If bootstrap tools require leases, infinite loop:
    - Can't call search_tools without lease
    - Can't get lease without calling get_tool_schema
    - Can't call get_tool_schema without lease
    """
    result = search_tools.fn(query="file")
    assert "read_file" in result or "write_file" in result

    ctx = mock_fastmcp_context(session_id="bootstrap_session")
    schema = await get_tool_schema.fn(tool_name="search_tools", ctx=ctx)
    assert "search_tools" in schema


@pytest.mark.asyncio
async def test_lease_consumption_only_on_success(redis_client):
    """
    CRITICAL: Failed tool calls must NOT consume lease.

    Security Risk: If failed calls consume lease, attacker could
    exhaust leases without successful execution (denial of service).
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )
    assert lease.calls_remaining == 3

    lease_check = await lease_manager.validate("test_session", "write_file")
    assert lease_check.calls_remaining == 3, "Validation should not consume lease"

    consumed = await lease_manager.consume("test_session", "write_file")
    assert consumed.calls_remaining == 2, "Successful call should consume lease"

    lease_check = await lease_manager.validate("test_session", "write_file")
    assert lease_check.calls_remaining == 2


@pytest.mark.asyncio
async def test_lease_not_granted_without_client_id(redis_client):
    """
    CRITICAL: Leases require stable client_id.

    Security Risk: If client_id is None or empty, lease scoping fails.
    All leases would be mixed together in Redis storage.
    """
    lease_none = await lease_manager.grant(
        client_id=None,
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_none is None, "Should not grant lease with None client_id"

    lease_empty = await lease_manager.grant(
        client_id="",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_empty is None, "Should not grant lease with empty client_id"

    lease_valid = await lease_manager.grant(
        client_id="valid_session_123",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease_valid is not None, "Should grant lease with valid client_id"


@pytest.mark.asyncio
async def test_calls_remaining_decrements_correctly(redis_client):
    """
    Verify calls_remaining decrements on each successful execution.

    Not critical for security but important for lease lifecycle.
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    for expected_remaining in [4, 3, 2, 1, 0]:
        consumed = await lease_manager.consume("test_session", "read_file")
        assert consumed.calls_remaining == expected_remaining

    exhausted = await lease_manager.validate("test_session", "read_file")
    assert exhausted is None, "Lease should be invalid when calls exhausted"


@pytest.mark.asyncio
async def test_lease_revocation(redis_client):
    """
    Verify lease revocation immediately invalidates lease.

    This is important for emergency lease cancellation or
    when mode changes require revoking all leases.
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    valid = await lease_manager.validate("test_session", "write_file")
    assert valid is not None

    revoked = await lease_manager.revoke("test_session", "write_file")
    assert revoked is True

    invalid = await lease_manager.validate("test_session", "write_file")
    assert invalid is None, "Revoked lease should be invalid"


@pytest.mark.asyncio
async def test_lease_ttl_enforced(redis_client):
    """
    CRITICAL: Verify TTL is enforced and leases auto-expire in Redis.

    Security Risk: If TTL not set correctly, leases persist forever.
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=2,
        calls_remaining=10,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    redis = await lease_manager._get_redis()
    key = lease_manager._lease_key("test_session", "read_file")
    ttl = await redis.ttl(key)
    assert 0 < ttl <= 2, f"TTL should be set to ~2 seconds, got {ttl}"

    await asyncio.sleep(2.5)

    exists = await redis.exists(key)
    assert exists == 0, "Lease should be auto-expired by Redis"


@pytest.mark.asyncio
async def test_lease_mode_consistency(redis_client, governance_in_permission):
    """
    Verify lease stores governance mode at time of issue.

    Current design: Lease remains valid until expiration regardless
    of mode changes. This test documents that behavior.
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease.mode_at_issue == "PERMISSION"

    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    valid = await lease_manager.validate("test_session", "write_file")
    assert valid is not None, "Lease remains valid after mode change"


@pytest.mark.asyncio
async def test_multiple_leases_per_session(redis_client):
    """
    Verify a session can have leases for multiple tools simultaneously.

    This ensures lease storage keys are unique per (client_id, tool_id) pair.
    """
    lease_read = await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    lease_write = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    assert lease_read is not None
    assert lease_write is not None

    read_check = await lease_manager.validate("test_session", "read_file")
    assert read_check.calls_remaining == 5

    write_check = await lease_manager.validate("test_session", "write_file")
    assert write_check.calls_remaining == 3

    await lease_manager.consume("test_session", "read_file")

    read_check = await lease_manager.validate("test_session", "read_file")
    assert read_check.calls_remaining == 4

    write_check = await lease_manager.validate("test_session", "write_file")
    assert write_check.calls_remaining == 3, "write_file lease should be unchanged"


@pytest.mark.asyncio
async def test_lease_fail_closed_on_redis_error(redis_client):
    """
    CRITICAL: Lease validation must fail-closed on Redis errors.

    Security Risk: If Redis is down and validation returns True by default,
    all tools become accessible without lease checks.
    """
    with patch.object(lease_manager, "_get_redis", new_callable=AsyncMock) as mock_redis:
        mock_redis.side_effect = aioredis.ConnectionError("Redis connection failed")

        lease = await lease_manager.validate("test_session", "read_file")
        assert lease is None, "SECURITY BREACH: Validation succeeded on Redis error"


@pytest.mark.asyncio
async def test_lease_expiration_race_condition(redis_client):
    """
    SECURITY: Verify lease expiration between validation and consumption.

    If TTL expires between validate() and consume(), consume() should fail closed.
    """
    await lease_manager.grant(
        client_id="race_session",
        tool_id="read_file",
        ttl_seconds=1,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    lease = await lease_manager.validate("race_session", "read_file")
    assert lease is not None

    await asyncio.sleep(1.5)

    consumed = await lease_manager.consume("race_session", "read_file")
    assert consumed is None, "Expired lease should return None (fail-closed)"


@pytest.mark.asyncio
async def test_empty_client_id_rejected_in_all_ops(redis_client):
    """
    SECURITY: Verify empty client_id fails closed in all lease operations.
    """
    lease = await lease_manager.grant("", "read_file", 300, 3, "PERMISSION")
    assert lease is None

    lease = await lease_manager.validate("", "read_file")
    assert lease is None

    consumed = await lease_manager.consume("", "read_file")
    assert consumed is None

    revoked = await lease_manager.revoke("", "read_file")
    assert revoked is False


@pytest.mark.asyncio
async def test_tool_id_empty_rejected(redis_client):
    """
    SECURITY: Verify empty tool_id is rejected when granting leases.
    """
    lease = await lease_manager.grant(
        client_id="tool_empty_session",
        tool_id="",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease is None


@pytest.mark.asyncio
async def test_negative_calls_remaining_rejected(redis_client):
    """
    SECURITY: Verify negative calls_remaining is rejected.
    """
    lease = await lease_manager.grant(
        client_id="negative_calls_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=-1,
        mode_at_issue="PERMISSION",
    )
    assert lease is None


@pytest.mark.asyncio
async def test_zero_ttl_rejected(redis_client):
    """
    SECURITY: Verify zero TTL is rejected.
    """
    lease = await lease_manager.grant(
        client_id="zero_ttl_session",
        tool_id="read_file",
        ttl_seconds=0,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )
    assert lease is None


@pytest.mark.asyncio
async def test_capability_token_roundtrip(redis_client):
    """
    SECURITY: Verify capability token is persisted with lease.
    """
    lease = await lease_manager.grant(
        client_id="token_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
        capability_token="token-123",
    )
    assert lease is not None
    assert lease.capability_token == "token-123"

    validated = await lease_manager.validate("token_session", "write_file")
    assert validated is not None
    assert validated.capability_token == "token-123"


@pytest.mark.asyncio
async def test_malformed_lease_json_handled_gracefully(redis_client):
    """
    SECURITY: Malformed lease JSON should fail closed.
    """
    redis = await lease_manager._get_redis()
    key = lease_manager._lease_key("malformed_client", "read_file")
    await redis.setex(key, 300, "{not-json")

    lease = await lease_manager.validate("malformed_client", "read_file")
    assert lease is None


@pytest.mark.asyncio
async def test_missing_required_fields_rejected(redis_client):
    """
    SECURITY: Missing lease fields should fail closed.
    """
    redis = await lease_manager._get_redis()
    key = lease_manager._lease_key("missing_fields", "read_file")
    await redis.setex(key, 300, json.dumps({"client_id": "missing_fields"}))

    lease = await lease_manager.validate("missing_fields", "read_file")
    assert lease is None


@pytest.mark.asyncio
async def test_special_characters_in_identifiers(redis_client):
    """
    SECURITY: Client and tool identifiers with special characters are handled.
    """
    client_id = "client-123@host"
    tool_id = "tool_name:with:colons"

    lease = await lease_manager.grant(
        client_id=client_id,
        tool_id=tool_id,
        ttl_seconds=300,
        calls_remaining=2,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    validated = await lease_manager.validate(client_id, tool_id)
    assert validated is not None
    assert validated.client_id == client_id
    assert validated.tool_id == tool_id


@pytest.mark.asyncio
async def test_purge_expired_does_not_delete_valid_leases(redis_client):
    """
    SECURITY: Purge should only delete expired leases, not valid ones.
    """
    await lease_manager.grant("purge_valid", "read_file", 300, 2, "PERMISSION")
    await lease_manager.grant("purge_expired", "write_file", 300, 2, "PERMISSION")

    redis = await lease_manager._get_redis()
    expired_key = lease_manager._lease_key("purge_expired", "write_file")

    expired_payload = {
        "client_id": "purge_expired",
        "tool_id": "write_file",
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
        "calls_remaining": 1,
        "mode_at_issue": "PERMISSION",
        "capability_token": None,
    }
    await redis.setex(expired_key, 300, json.dumps(expired_payload))

    purged = await lease_manager.purge_expired()
    assert purged >= 1

    valid = await lease_manager.validate("purge_valid", "read_file")
    assert valid is not None

    expired = await lease_manager.validate("purge_expired", "write_file")
    assert expired is None
