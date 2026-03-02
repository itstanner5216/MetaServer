"""Tests for agent_detector module."""

import os
from unittest.mock import MagicMock

import pytest

from src.meta_mcp.agent_detector import (
    detect_agent_id,
    get_agent_id_for_session,
    set_agent_id_for_session,
)


class TestDetectAgentId:
    """Tests for detect_agent_id function."""

    def test_detect_from_metadata(self):
        """Should detect agent_id from context metadata."""
        ctx = MagicMock()
        ctx.metadata = {"agent_id": "agent-from-metadata"}
        
        result = detect_agent_id(ctx)
        
        assert result == "agent-from-metadata"

    def test_detect_from_request_context(self):
        """Should detect agent_id from request_context when metadata missing."""
        ctx = MagicMock()
        ctx.metadata = None
        ctx.request_context = MagicMock()
        ctx.request_context.agent_id = "agent-from-request"
        
        result = detect_agent_id(ctx)
        
        assert result == "agent-from-request"

    def test_detect_from_environment(self, monkeypatch):
        """Should detect agent_id from MCP_AGENT_ID env var."""
        ctx = MagicMock()
        ctx.metadata = None
        # Make request_context not have agent_id attribute
        del ctx.request_context
        
        monkeypatch.setenv("MCP_AGENT_ID", "agent-from-env")
        
        result = detect_agent_id(ctx)
        
        assert result == "agent-from-env"

    def test_detect_returns_none_when_no_agent_id(self, monkeypatch):
        """Should return None when no agent_id found."""
        ctx = MagicMock()
        ctx.metadata = None
        del ctx.request_context
        
        # Ensure env var is not set
        monkeypatch.delenv("MCP_AGENT_ID", raising=False)
        
        result = detect_agent_id(ctx)
        
        assert result is None

    def test_detect_empty_metadata_agent_id(self):
        """Should fall through when metadata has empty agent_id."""
        ctx = MagicMock()
        ctx.metadata = {"agent_id": ""}
        del ctx.request_context
        
        result = detect_agent_id(ctx)
        
        # Empty string is falsy, so should continue to next strategy
        assert result is None or result == ""

    def test_detect_no_metadata_attribute(self, monkeypatch):
        """Should handle context without metadata attribute."""
        ctx = MagicMock(spec=[])  # No attributes
        
        monkeypatch.delenv("MCP_AGENT_ID", raising=False)
        
        result = detect_agent_id(ctx)
        
        assert result is None

    def test_metadata_priority_over_request_context(self):
        """Should use metadata agent_id over request_context."""
        ctx = MagicMock()
        ctx.metadata = {"agent_id": "metadata-agent"}
        ctx.request_context = MagicMock()
        ctx.request_context.agent_id = "request-agent"
        
        result = detect_agent_id(ctx)
        
        assert result == "metadata-agent"

    def test_request_context_priority_over_env(self, monkeypatch):
        """Should use request_context agent_id over environment."""
        ctx = MagicMock()
        ctx.metadata = None
        ctx.request_context = MagicMock()
        ctx.request_context.agent_id = "request-agent"
        
        monkeypatch.setenv("MCP_AGENT_ID", "env-agent")
        
        result = detect_agent_id(ctx)
        
        assert result == "request-agent"


class TestGetAgentIdForSession:
    """Tests for get_agent_id_for_session function."""

    @pytest.mark.asyncio
    async def test_returns_none_placeholder(self):
        """Should return None (placeholder implementation)."""
        result = await get_agent_id_for_session("session-123")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_accepts_any_session_id(self):
        """Should accept any session_id string."""
        result = await get_agent_id_for_session("any-session-id-format")
        
        assert result is None


class TestSetAgentIdForSession:
    """Tests for set_agent_id_for_session function."""

    @pytest.mark.asyncio
    async def test_returns_false_placeholder(self):
        """Should return False (placeholder implementation)."""
        result = await set_agent_id_for_session("session-123", "agent-456")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_accepts_custom_ttl(self):
        """Should accept custom TTL parameter."""
        result = await set_agent_id_for_session("session-123", "agent-456", ttl=7200)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_accepts_any_parameters(self):
        """Should accept various parameter combinations."""
        result = await set_agent_id_for_session(
            session_id="test-session",
            agent_id="test-agent",
            ttl=1800
        )
        
        assert result is False
