"""Tests for MCP notification emission.

NOTE: Notification emission is not implemented yet. All tests in this module
are skipped until Phase 8 is complete and tools/list_changed notifications are
emitted by lease operations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.meta_mcp.leases.manager import LeaseManager


@pytest.fixture
async def lease_manager(redis_client):
    """Provide a lease manager with a clean Redis connection."""
    manager = LeaseManager()
    yield manager
    await manager.close()


@pytest.mark.skip(reason="Notification emission not yet implemented")
@pytest.mark.asyncio
class TestNotificationEmission:
    """Test MCP notification emission on lease events."""

    @pytest.mark.requires_redis
    async def test_notification_on_lease_grant(self, lease_manager):
        """Notification emitted when lease granted."""
        with patch("src.meta_mcp.leases.manager.emit_notification", create=True) as mock_emit:
            await lease_manager.grant(
                client_id="test_client",
                tool_id="write_file",
                ttl_seconds=300,
                calls_remaining=3,
                mode_at_issue="PERMISSION",
            )

            mock_emit.assert_called_once()
            call_args = mock_emit.call_args
            assert call_args.args[0] == "tools/list_changed"
            payload = call_args.args[1]
            assert payload["client_id"] == "test_client"
            assert payload["tool_id"] == "write_file"

    @pytest.mark.requires_redis
    async def test_notification_on_lease_consume(self, lease_manager):
        """Notification emitted when lease consumed."""
        await lease_manager.grant(
            client_id="test_client",
            tool_id="write_file",
            ttl_seconds=300,
            calls_remaining=1,
            mode_at_issue="PERMISSION",
        )

        with patch("src.meta_mcp.leases.manager.emit_notification", create=True) as mock_emit:
            await lease_manager.consume("test_client", "write_file")

            if mock_emit.called:
                call_args = mock_emit.call_args
                assert call_args.args[0] == "tools/list_changed"
                payload = call_args.args[1]
                assert payload["client_id"] == "test_client"
                assert payload["tool_id"] == "write_file"

    @pytest.mark.requires_redis
    async def test_notification_on_lease_revoke(self, lease_manager):
        """Notification emitted when lease revoked."""
        await lease_manager.grant(
            client_id="test_client",
            tool_id="write_file",
            ttl_seconds=300,
            calls_remaining=3,
            mode_at_issue="PERMISSION",
        )

        with patch("src.meta_mcp.leases.manager.emit_notification", create=True) as mock_emit:
            await lease_manager.revoke("test_client", "write_file")

            mock_emit.assert_called_once()
            assert mock_emit.call_args.args[0] == "tools/list_changed"

    @pytest.mark.requires_redis
    async def test_notification_on_lease_expire(self, lease_manager):
        """Notification emitted when lease expires."""
        await lease_manager.grant(
            client_id="test_client",
            tool_id="write_file",
            ttl_seconds=1,
            calls_remaining=3,
            mode_at_issue="PERMISSION",
        )

        await asyncio.sleep(2)

        with patch("src.meta_mcp.leases.manager.emit_notification", create=True) as mock_emit:
            await lease_manager.purge_expired()

            assert mock_emit.called

    @pytest.mark.requires_redis
    async def test_notification_with_multiple_clients(self, lease_manager):
        """Each client gets notifications for their lease changes."""
        with patch("src.meta_mcp.leases.manager.emit_notification", create=True) as mock_emit:
            await lease_manager.grant(
                client_id="client_1",
                tool_id="write_file",
                ttl_seconds=300,
                calls_remaining=1,
                mode_at_issue="PERMISSION",
            )
            await lease_manager.grant(
                client_id="client_2",
                tool_id="write_file",
                ttl_seconds=300,
                calls_remaining=1,
                mode_at_issue="PERMISSION",
            )

            assert mock_emit.call_count >= 2

    @pytest.mark.requires_redis
    async def test_no_notification_when_disabled(self, lease_manager):
        """No notifications if feature disabled."""
        from src.meta_mcp.config import Config

        if not hasattr(Config, "ENABLE_NOTIFICATIONS"):
            pytest.skip("Notification config flag not available yet")

        original = Config.ENABLE_NOTIFICATIONS
        try:
            Config.ENABLE_NOTIFICATIONS = False

            with patch("src.meta_mcp.leases.manager.emit_notification", create=True) as mock_emit:
                await lease_manager.grant(
                    client_id="test_client",
                    tool_id="write_file",
                    ttl_seconds=300,
                    calls_remaining=1,
                    mode_at_issue="PERMISSION",
                )

                assert not mock_emit.called

        finally:
            Config.ENABLE_NOTIFICATIONS = original
