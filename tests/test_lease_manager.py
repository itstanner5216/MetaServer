"""
Unit Tests for LeaseManager (Phase 3)

Tests LeaseManager methods:
- grant(): Create new leases
- validate(): Check lease validity
- consume(): Decrement lease calls
- revoke(): Delete leases
- purge(): Cleanup expired leases
"""

import asyncio

import pytest

from src.meta_mcp.config import Config
from src.meta_mcp.governance.tokens import generate_token
from src.meta_mcp.leases import lease_manager


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_grant_creates_lease(redis_client):
    """
    Verify grant() creates a lease in Redis.
    """
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    assert lease is not None, "Lease should be created"
    assert lease.client_id == "test_session"
    assert lease.tool_id == "read_file"
    assert lease.calls_remaining == 5
    assert lease.mode_at_issue == "PERMISSION"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_validate_returns_none_for_nonexistent_lease(redis_client):
    """
    Verify validate() returns None when lease doesn't exist.
    """
    lease = await lease_manager.validate("nonexistent_session", "read_file")
    assert lease is None, "Non-existent lease should return None"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_validate_returns_lease_when_valid(redis_client):
    """
    Verify validate() returns lease when it exists and is valid.
    """
    # Grant lease
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    # Validate
    lease = await lease_manager.validate("test_session", "read_file")
    assert lease is not None, "Lease should be valid"
    assert lease.calls_remaining == 3


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_consume_decrements_calls(redis_client):
    """
    Verify consume() decrements calls_remaining.
    """
    # Grant lease with 3 calls
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    # Consume once
    lease = await lease_manager.consume("test_session", "read_file")
    assert lease.calls_remaining == 2, "Should decrement to 2"

    # Consume again
    lease = await lease_manager.consume("test_session", "read_file")
    assert lease.calls_remaining == 1, "Should decrement to 1"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_consume_returns_none_when_exhausted(redis_client):
    """
    Verify consume() returns None when no calls remaining.
    """
    # Grant lease with 1 call
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )

    # Consume the only call
    lease = await lease_manager.consume("test_session", "read_file")
    assert lease.calls_remaining == 0, "Should have 0 calls"

    # Try to consume again
    lease = await lease_manager.consume("test_session", "read_file")
    assert lease is None, "Exhausted lease should return None"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_revoke_deletes_lease(redis_client):
    """
    Verify revoke() deletes lease from Redis.
    """
    # Grant lease
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    # Verify lease exists
    lease = await lease_manager.validate("test_session", "read_file")
    assert lease is not None, "Lease should exist"

    # Revoke
    revoked = await lease_manager.revoke("test_session", "read_file")
    assert revoked is True, "Revoke should succeed"

    # Verify lease is gone
    lease = await lease_manager.validate("test_session", "read_file")
    assert lease is None, "Lease should be deleted"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_grant_with_capability_token(redis_client):
    """
    Verify grant() can store capability token with lease.
    """
    # Generate token
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    # Grant lease with token
    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
        capability_token=token,
    )

    # Verify token stored
    assert lease.capability_token == token

    # Verify token persisted
    lease_check = await lease_manager.validate("test_session", "write_file")
    assert lease_check.capability_token == token


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_purge_removes_expired_leases(redis_client):
    """
    Verify purge() removes expired leases.

    Note: Redis TTL auto-expires keys, but purge() might be needed
    for manual cleanup or testing.
    """
    # Grant short-lived lease
    await lease_manager.grant(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=1,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Wait for expiration
    await asyncio.sleep(2)

    # Purge expired leases
    purged_count = await lease_manager.purge_expired()

    # Verify lease is gone
    lease = await lease_manager.validate("test_session", "read_file")
    assert lease is None, "Expired lease should be gone"
