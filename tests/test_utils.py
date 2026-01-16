"""Shared utilities for testing MetaMCP components."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable
from unittest.mock import Mock

from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry


def create_test_tool(
    tool_id: str,
    risk_level: str = "safe",
    requires_permission: bool = False,
    **kwargs: Any,
) -> ToolRecord:
    """
    Create a ToolRecord for testing with sensible defaults.

    Args:
        tool_id: Tool identifier
        risk_level: safe/sensitive/dangerous
        requires_permission: Whether approval required
        **kwargs: Override any ToolRecord fields

    Returns:
        ToolRecord instance
    """
    defaults: dict[str, Any] = {
        "tool_id": tool_id,
        "server_id": "test_server",
        "description_1line": f"Test tool: {tool_id}",
        "description_full": f"Full description of {tool_id}",
        "tags": ["test", risk_level],
        "risk_level": risk_level,
        "requires_permission": requires_permission,
        "schema_min": {"type": "object"},
        "schema_full": {"type": "object", "properties": {}},
    }
    defaults.update(kwargs)
    return ToolRecord(**defaults)


def create_test_registry(tools: Iterable[ToolRecord]) -> ToolRegistry:
    """
    Create a registry populated with test tools.

    Args:
        tools: List of ToolRecord objects to add

    Returns:
        ToolRegistry with tools added
    """
    registry = ToolRegistry()
    for tool in tools:
        registry.add_for_testing(tool)
    return registry


async def assert_audit_log_contains(
    event_type: str,
    tool_name: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Assert that audit log contains event matching criteria.

    Args:
        event_type: Event type to search for
        tool_name: Optional tool name filter
        **kwargs: Additional fields to match

    Raises:
        AssertionError if not found
    """
    import json

    from src.meta_mcp.audit import audit_logger

    log_path = audit_logger.log_path
    if not log_path.exists():
        raise AssertionError(f"Audit log not found at {log_path}")

    with open(log_path) as log_file:
        logs = [json.loads(line) for line in log_file if line.strip()]

    for log in logs:
        if log.get("event") != event_type:
            continue
        if tool_name and log.get("tool_name") != tool_name:
            continue
        if all(log.get(key) == value for key, value in kwargs.items()):
            return

    raise AssertionError(
        f"Audit log does not contain {event_type} event for tool={tool_name} with {kwargs}"
    )


def mock_fastmcp_context(
    session_id: str = "test_session",
    client_id: str = "test_client",
    **kwargs: Any,
) -> Mock:
    """
    Create a mock FastMCP Context for testing.

    Args:
        session_id: Session identifier
        client_id: Client identifier
        **kwargs: Additional context attributes

    Returns:
        Mock Context object
    """
    ctx = Mock()
    ctx.session_id = session_id
    ctx.client_id = client_id

    for key, value in kwargs.items():
        setattr(ctx, key, value)

    return ctx


async def cleanup_test_files(*paths: str) -> None:
    """
    Clean up test files/directories.

    Args:
        *paths: File/directory paths to remove
    """
    import os
    import shutil

    for path in paths:
        try:
            if os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except FileNotFoundError:
            pass


async def wait_for_condition(
    condition_fn: Callable[[], Awaitable[bool]],
    timeout: float = 5.0,
    interval: float = 0.1,
    error_msg: str = "Condition not met",
) -> None:
    """
    Wait for async condition to become true.

    Args:
        condition_fn: Async function returning bool
        timeout: Max seconds to wait
        interval: Check interval in seconds
        error_msg: Error message if timeout

    Raises:
        TimeoutError if condition not met
    """
    import asyncio
    import time

    start = time.time()
    while time.time() - start < timeout:
        if await condition_fn():
            return
        await asyncio.sleep(interval)

    raise TimeoutError(error_msg)
