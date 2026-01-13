"""Pytest fixtures and test utilities for Meta MCP Server test suite."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from redis import asyncio as aioredis

from src.meta_mcp.audit import AuditLogger
from src.meta_mcp.state import ExecutionMode, governance_state


# ============================================================================
# REDIS FIXTURES
# ============================================================================


@pytest.fixture
async def redis_client():
    """
    Provide clean Redis connection with flush before and after test.

    Yields:
        Redis client instance with clean database

    Cleanup:
        Flushes Redis database after test
    """
    # Create Redis client
    client = aioredis.from_url(
        "redis://localhost:6379",
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    try:
        # Flush database before test
        await client.flushdb()

        yield client

    finally:
        # Flush database after test for isolation
        await client.flushdb()
        await client.aclose()


# ============================================================================
# GOVERNANCE MODE FIXTURES
# ============================================================================


@pytest.fixture
async def governance_in_read_only(redis_client):
    """
    Set governance mode to READ_ONLY for test.

    Args:
        redis_client: Redis client fixture

    Yields:
        None (mode is set in Redis)

    Cleanup:
        Resets mode to PERMISSION
    """
    # Set READ_ONLY mode
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    yield

    # Reset to PERMISSION (fail-safe default)
    await governance_state.set_mode(ExecutionMode.PERMISSION)


@pytest.fixture
async def governance_in_bypass(redis_client):
    """
    Set governance mode to BYPASS for test.

    Args:
        redis_client: Redis client fixture

    Yields:
        None (mode is set in Redis)

    Cleanup:
        Resets mode to PERMISSION
    """
    # Set BYPASS mode
    await governance_state.set_mode(ExecutionMode.BYPASS)

    yield

    # Reset to PERMISSION (fail-safe default)
    await governance_state.set_mode(ExecutionMode.PERMISSION)


@pytest.fixture
async def governance_in_permission(redis_client):
    """
    Set governance mode to PERMISSION (default).

    Args:
        redis_client: Redis client fixture

    Yields:
        None (mode is set in Redis)

    Cleanup:
        Resets mode to PERMISSION
    """
    # Set PERMISSION mode (explicit)
    await governance_state.set_mode(ExecutionMode.PERMISSION)

    yield

    # Mode already at PERMISSION, no cleanup needed
    await governance_state.set_mode(ExecutionMode.PERMISSION)


# ============================================================================
# FASTMCP CONTEXT MOCK FIXTURES
# ============================================================================


@pytest.fixture
def mock_fastmcp_context():
    """
    Create mock FastMCP Context object with request_context.

    Returns:
        Mock Context object with:
        - request_context.tool_name
        - request_context.arguments
        - request_context.session_id
        - session_id (kept in sync with request_context.session_id)
        - elicit() async method
    """
    class MockContext:
        def __init__(self):
            self.request_context = MagicMock()
            self.request_context.tool_name = "write_file"
            self.request_context.arguments = {"path": "test.txt", "content": "test content"}
            self.request_context.session_id = "test-session-123"
            self.elicit = AsyncMock()

        @property
        def session_id(self):
            return self.request_context.session_id

        @session_id.setter
        def session_id(self, value):
            self.request_context.session_id = value

    return MockContext()


# ============================================================================
# ELICITATION MOCK FIXTURES
# ============================================================================


@pytest.fixture
def mock_elicit_approve():
    """
    Mock elicitation returning approval.

    Returns:
        AsyncMock that returns approval-like response
    """

    async def _approve(*args, **kwargs):
        # Return mock AcceptedElicitation with approval response
        result = MagicMock()
        result.data = "approve"
        return result

    return AsyncMock(side_effect=_approve)


@pytest.fixture
def mock_elicit_deny():
    """
    Mock elicitation returning denial.

    Returns:
        AsyncMock that returns denial-like response
    """

    async def _deny(*args, **kwargs):
        # Return mock AcceptedElicitation with denial response
        result = MagicMock()
        result.data = "deny"
        return result

    return AsyncMock(side_effect=_deny)


@pytest.fixture
def mock_elicit_timeout():
    """
    Mock elicitation that times out.

    Returns:
        AsyncMock that raises asyncio.TimeoutError
    """

    async def _timeout(*args, **kwargs):
        await asyncio.sleep(0.1)  # Small delay
        raise asyncio.TimeoutError("Elicitation timed out")

    return AsyncMock(side_effect=_timeout)


@pytest.fixture
def mock_elicit_declined():
    """
    Mock elicitation returning DeclinedElicitation.

    Returns:
        AsyncMock that returns object without 'data' attribute
    """

    async def _declined(*args, **kwargs):
        # Return mock DeclinedElicitation (no .data attribute)
        result = MagicMock(spec=[])  # Empty spec = no attributes
        return result

    return AsyncMock(side_effect=_declined)


@pytest.fixture
def mock_elicit_cancelled():
    """
    Mock elicitation returning CancelledElicitation.

    Returns:
        AsyncMock that returns object without 'data' attribute
    """

    async def _cancelled(*args, **kwargs):
        # Return mock CancelledElicitation (no .data attribute)
        result = MagicMock(spec=[])  # Empty spec = no attributes
        return result

    return AsyncMock(side_effect=_cancelled)


# ============================================================================
# ELEVATION FIXTURES
# ============================================================================


@pytest.fixture
async def granted_elevation(redis_client):
    """
    Pre-grant scoped elevation for a specific tool/path/session.

    Args:
        redis_client: Redis client fixture

    Returns:
        Callable that grants elevation: grant(tool_name, context_key, session_id, ttl=300)
    """

    async def _grant(
        tool_name: str, context_key: str, session_id: str, ttl: int = 300
    ) -> str:
        """
        Grant elevation and return the hash key.

        Args:
            tool_name: Tool name
            context_key: Context key (e.g., file path)
            session_id: Session ID
            ttl: Time-to-live in seconds

        Returns:
            Elevation hash key
        """
        hash_key = governance_state.compute_elevation_hash(
            tool_name=tool_name, context_key=context_key, session_id=session_id
        )
        await governance_state.grant_elevation(hash_key, ttl)
        return hash_key

    return _grant


# ============================================================================
# AUDIT LOG FIXTURES
# ============================================================================


@pytest.fixture
def audit_log_path(tmp_path):
    """
    Provide temporary audit log file for test isolation.

    Args:
        tmp_path: pytest temporary directory fixture

    Returns:
        Path to temporary audit.jsonl file

    Cleanup:
        Temporary directory automatically cleaned up by pytest
    """
    # Create temporary audit log path
    log_path = tmp_path / "audit.jsonl"

    # Set environment variable to use this path
    import os

    original_path = os.environ.get("AUDIT_LOG_PATH")
    os.environ["AUDIT_LOG_PATH"] = str(log_path)

    yield log_path

    # Restore original environment variable
    if original_path is not None:
        os.environ["AUDIT_LOG_PATH"] = original_path
    else:
        os.environ.pop("AUDIT_LOG_PATH", None)


# ============================================================================
# LEASE FIXTURES
# ============================================================================


@pytest.fixture
async def lease_for_tool(redis_client):
    """
    Grant lease for a specific tool to the default client.

    This fixture establishes the lease-first pattern required by the middleware.
    The middleware validates leases before allowing tool execution (except bootstrap tools).

    Args:
        redis_client: Redis client fixture

    Returns:
        Callable that grants lease: grant(tool_name, calls=5, ttl=300, mode="PERMISSION")
    """
    from src.meta_mcp.leases import lease_manager

    async def _grant(
        tool_name: str,
        calls: int = 5,
        ttl: int = 300,
        mode: str = "PERMISSION",
        client_id: Optional[str] = None,
    ) -> None:
        """
        Grant lease for a tool.

        Args:
            tool_name: Tool name to grant lease for
            calls: Number of calls remaining (default: 5)
            ttl: Time-to-live in seconds (default: 300)
            mode: Mode at issue (default: "PERMISSION")
        """
        # Default to the mock context session_id used in tests
        effective_client_id = client_id or "test-session-123"

        lease = await lease_manager.grant(
            client_id=effective_client_id,
            tool_id=tool_name,
            ttl_seconds=ttl,
            calls_remaining=calls,
            mode_at_issue=mode,
        )

        if lease is None:
            raise RuntimeError(f"Failed to grant lease for tool '{tool_name}'")

    return _grant


# ============================================================================
# HELPER UTILITIES
# ============================================================================


def read_audit_log(log_path: Path) -> list[Dict[str, Any]]:
    """
    Read and parse audit log file.

    Args:
        log_path: Path to audit.jsonl file

    Returns:
        List of audit log entries (parsed JSON objects)
    """
    import json

    if not log_path.exists():
        return []

    entries = []
    with open(log_path, "r") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


# Export helper for use in tests
__all__ = [
    "redis_client",
    "governance_in_read_only",
    "governance_in_bypass",
    "governance_in_permission",
    "mock_fastmcp_context",
    "mock_elicit_approve",
    "mock_elicit_deny",
    "mock_elicit_timeout",
    "mock_elicit_declined",
    "mock_elicit_cancelled",
    "granted_elevation",
    "lease_for_tool",
    "audit_log_path",
    "read_audit_log",
]
