"""
Unit Tests for ToolLease Data Models (Phase 3)

Tests the ToolLease dataclass:
- Creation and validation
- Expiration logic
- Consumption tracking
- Invariant enforcement
"""

from datetime import datetime

import pytest

from src.meta_mcp.leases.models import ToolLease


@pytest.mark.asyncio
@pytest.mark.unit
async def test_lease_creation():
    """
    Verify ToolLease can be created with valid parameters.
    """
    lease = ToolLease.create(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    assert lease.client_id == "test_session"
    assert lease.tool_id == "read_file"
    assert lease.calls_remaining == 3
    assert lease.mode_at_issue == "PERMISSION"
    assert lease.expires_at > lease.granted_at


@pytest.mark.asyncio
@pytest.mark.unit
async def test_lease_expiration_check():
    """
    Verify is_expired() correctly identifies expired leases.
    """
    import asyncio

    # Create lease with 1 second TTL
    lease = ToolLease.create(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=1,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Not expired initially
    assert not lease.is_expired()

    # Wait for expiration
    await asyncio.sleep(2)

    # Now expired
    assert lease.is_expired()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_lease_can_consume():
    """
    Verify can_consume() checks both expiration and calls_remaining.
    """
    # Create lease
    lease = ToolLease.create(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    # Can consume initially
    assert lease.can_consume()

    # Exhaust calls
    lease.calls_remaining = 0
    assert not lease.can_consume()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_lease_validation_errors():
    """
    Verify ToolLease.create() raises errors for invalid parameters.
    """
    # Invalid TTL
    with pytest.raises(ValueError):
        ToolLease.create(
            client_id="test",
            tool_id="read_file",
            ttl_seconds=0,  # Invalid
            calls_remaining=1,
            mode_at_issue="PERMISSION",
        )

    # Invalid calls_remaining
    with pytest.raises(ValueError):
        ToolLease.create(
            client_id="test",
            tool_id="read_file",
            ttl_seconds=300,
            calls_remaining=-1,  # Invalid
            mode_at_issue="PERMISSION",
        )

    # Empty client_id
    with pytest.raises(ValueError):
        ToolLease.create(
            client_id="",  # Invalid
            tool_id="read_file",
            ttl_seconds=300,
            calls_remaining=1,
            mode_at_issue="PERMISSION",
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_lease_serialization():
    """
    Verify ToolLease can be serialized to/from dict for Redis storage.
    """
    import json
    from dataclasses import asdict

    # Create lease
    lease = ToolLease.create(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
    )

    # Serialize
    lease_dict = asdict(lease)
    lease_dict["granted_at"] = lease.granted_at.isoformat()
    lease_dict["expires_at"] = lease.expires_at.isoformat()
    lease_json = json.dumps(lease_dict)

    # Deserialize
    loaded_dict = json.loads(lease_json)
    loaded_dict["granted_at"] = datetime.fromisoformat(loaded_dict["granted_at"])
    loaded_dict["expires_at"] = datetime.fromisoformat(loaded_dict["expires_at"])
    loaded_lease = ToolLease(**loaded_dict)

    # Verify equality
    assert loaded_lease.client_id == lease.client_id
    assert loaded_lease.tool_id == lease.tool_id
    assert loaded_lease.calls_remaining == lease.calls_remaining
