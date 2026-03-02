"""Tests for lease manager module coverage.

Covers grant, validate, consume, revoke, purge, close, and notification callbacks.
Uses mocked Redis to avoid requiring a running Redis instance.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.meta_mcp.leases.manager import LeaseManager
from src.meta_mcp.leases.models import ToolLease


def _make_lease_json(
    client_id="client-1",
    tool_id="write_file",
    ttl_seconds=300,
    calls_remaining=5,
    mode_at_issue="PERMISSION",
    capability_token=None,
):
    now = datetime.now(timezone.utc)
    return json.dumps({
        "client_id": client_id,
        "tool_id": tool_id,
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        "calls_remaining": calls_remaining,
        "mode_at_issue": mode_at_issue,
        "capability_token": capability_token,
    })


def _make_expired_lease_json(client_id="client-1", tool_id="write_file"):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    return json.dumps({
        "client_id": client_id,
        "tool_id": tool_id,
        "granted_at": (past - timedelta(hours=1)).isoformat(),
        "expires_at": past.isoformat(),
        "calls_remaining": 5,
        "mode_at_issue": "PERMISSION",
        "capability_token": None,
    })


class TestLeaseManagerGrant:
    @pytest.mark.asyncio
    async def test_grant_success(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.grant(
                client_id="client-1",
                tool_id="write_file",
                ttl_seconds=300,
                calls_remaining=5,
                mode_at_issue="PERMISSION",
            )
        assert lease is not None
        assert lease.client_id == "client-1"
        assert lease.tool_id == "write_file"
        assert lease.calls_remaining == 5
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_grant_empty_client_id(self):
        manager = LeaseManager()
        lease = await manager.grant(
            client_id="",
            tool_id="write_file",
            ttl_seconds=300,
            calls_remaining=5,
            mode_at_issue="PERMISSION",
        )
        assert lease is None

    @pytest.mark.asyncio
    async def test_grant_whitespace_client_id(self):
        manager = LeaseManager()
        lease = await manager.grant(
            client_id="   ",
            tool_id="write_file",
            ttl_seconds=300,
            calls_remaining=5,
            mode_at_issue="PERMISSION",
        )
        assert lease is None

    @pytest.mark.asyncio
    async def test_grant_redis_error(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("connection lost"))

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.grant(
                client_id="client-1",
                tool_id="write_file",
                ttl_seconds=300,
                calls_remaining=5,
                mode_at_issue="PERMISSION",
            )
        assert lease is None

    @pytest.mark.asyncio
    async def test_grant_invalid_ttl(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.grant(
                client_id="client-1",
                tool_id="write_file",
                ttl_seconds=-1,
                calls_remaining=5,
                mode_at_issue="PERMISSION",
            )
        assert lease is None

    @pytest.mark.asyncio
    async def test_grant_with_capability_token(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.grant(
                client_id="client-1",
                tool_id="write_file",
                ttl_seconds=300,
                calls_remaining=5,
                mode_at_issue="PERMISSION",
                capability_token="tok-123",
            )
        assert lease is not None
        assert lease.capability_token == "tok-123"


class TestLeaseManagerValidate:
    @pytest.mark.asyncio
    async def test_validate_success(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=_make_lease_json())

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.validate("client-1", "write_file")
        assert lease is not None
        assert lease.client_id == "client-1"

    @pytest.mark.asyncio
    async def test_validate_not_found(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.validate("client-1", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_validate_expired(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=_make_expired_lease_json())
        mock_redis.delete = AsyncMock()

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.validate("client-1", "write_file")
        assert lease is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_exhausted(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(
            return_value=_make_lease_json(calls_remaining=0)
        )

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.validate("client-1", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_validate_empty_client_id(self):
        manager = LeaseManager()
        lease = await manager.validate("", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_validate_redis_error(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("connection lost"))

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.validate("client-1", "write_file")
        assert lease is None


class TestLeaseManagerConsume:
    @pytest.mark.asyncio
    async def test_consume_success(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        lease_json = _make_lease_json(calls_remaining=3)
        mock_redis.eval = AsyncMock(return_value=[1, lease_json, 290])

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.consume("client-1", "write_file")
        assert lease is not None
        assert lease.client_id == "client-1"

    @pytest.mark.asyncio
    async def test_consume_exhausted(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        lease_json = _make_lease_json(calls_remaining=0)
        mock_redis.eval = AsyncMock(return_value=[1, lease_json, 0])

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.consume("client-1", "write_file")
        assert lease is not None
        assert lease.calls_remaining == 0

    @pytest.mark.asyncio
    async def test_consume_not_found(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[0])

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.consume("client-1", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_consume_empty_result(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=None)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.consume("client-1", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_consume_no_lease_json(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[1, None, 0])

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.consume("client-1", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_consume_empty_client_id(self):
        manager = LeaseManager()
        lease = await manager.consume("", "write_file")
        assert lease is None

    @pytest.mark.asyncio
    async def test_consume_redis_error(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(side_effect=Exception("connection lost"))

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            lease = await manager.consume("client-1", "write_file")
        assert lease is None


class TestLeaseManagerRevoke:
    @pytest.mark.asyncio
    async def test_revoke_success(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            result = await manager.revoke("client-1", "write_file")
        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_not_found(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=0)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            result = await manager.revoke("client-1", "write_file")
        assert result is True  # Still returns True even if not found

    @pytest.mark.asyncio
    async def test_revoke_empty_client_id(self):
        manager = LeaseManager()
        result = await manager.revoke("", "write_file")
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_redis_error(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=Exception("connection lost"))

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            result = await manager.revoke("client-1", "write_file")
        assert result is False


class TestLeaseManagerPurgeExpired:
    @pytest.mark.asyncio
    async def test_purge_expired_none(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()

        async def empty_scan_iter(*args, **kwargs):
            return
            yield  # Make it an async generator

        mock_redis.scan_iter = empty_scan_iter

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            count = await manager.purge_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_purge_expired_with_expired_keys(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        expired_json = _make_expired_lease_json()

        async def scan_iter(*args, **kwargs):
            yield "lease:client-1:write_file"

        mock_redis.scan_iter = scan_iter
        mock_redis.get = AsyncMock(return_value=expired_json)
        mock_redis.delete = AsyncMock(return_value=1)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            count = await manager.purge_expired()
        assert count == 1

    @pytest.mark.asyncio
    async def test_purge_expired_with_valid_keys(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        valid_json = _make_lease_json(ttl_seconds=3600)

        async def scan_iter(*args, **kwargs):
            yield "lease:client-1:write_file"

        mock_redis.scan_iter = scan_iter
        mock_redis.get = AsyncMock(return_value=valid_json)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            count = await manager.purge_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_purge_expired_redis_error(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()
        async def failing_scan_iter(*args, **kwargs):
            raise Exception("connection lost")
            yield

        mock_redis.scan_iter = failing_scan_iter

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            count = await manager.purge_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_purge_expired_key_deleted_between_scan_and_get(self):
        manager = LeaseManager()
        mock_redis = AsyncMock()

        async def scan_iter(*args, **kwargs):
            yield "lease:client-1:write_file"

        mock_redis.scan_iter = scan_iter
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            count = await manager.purge_expired()
        assert count == 0


class TestLeaseManagerClose:
    @pytest.mark.asyncio
    async def test_close(self):
        manager = LeaseManager()
        with patch("src.meta_mcp.leases.manager.close_redis_client", new_callable=AsyncMock):
            await manager.close()
            assert manager._redis_client is None


class TestLeaseManagerNotifications:
    @pytest.mark.asyncio
    async def test_register_and_emit_sync_callback(self):
        manager = LeaseManager()
        called_with = []

        def sync_callback(client_id):
            called_with.append(client_id)

        manager.register_notification_callback(sync_callback)
        await manager._emit_list_changed("client-1")
        assert called_with == ["client-1"]

    @pytest.mark.asyncio
    async def test_register_and_emit_async_callback(self):
        manager = LeaseManager()
        called_with = []

        async def async_callback(client_id):
            called_with.append(client_id)

        manager.register_notification_callback(async_callback)
        await manager._emit_list_changed("client-1")
        assert called_with == ["client-1"]

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self):
        manager = LeaseManager()

        def bad_callback(client_id):
            raise RuntimeError("callback error")

        manager.register_notification_callback(bad_callback)
        # Should not raise
        await manager._emit_list_changed("client-1")

    def test_unregister_callback(self):
        manager = LeaseManager()

        def callback(client_id):
            pass

        manager.register_notification_callback(callback)
        assert callback in manager._notification_callbacks
        manager.unregister_notification_callback(callback)
        assert callback not in manager._notification_callbacks

    def test_unregister_nonexistent_callback(self):
        manager = LeaseManager()

        def callback(client_id):
            pass

        # Should not raise
        manager.unregister_notification_callback(callback)

    def test_lease_key_generation(self):
        key = LeaseManager._lease_key("client-1", "write_file")
        assert key == "lease:client-1:write_file"
