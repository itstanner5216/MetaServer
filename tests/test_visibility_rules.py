"""Tests for tool visibility filtering in list_tools."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from fastmcp.server.middleware import MiddlewareContext
from mcp import types as mcp_types

import pytest

from src.meta_mcp.middleware import GovernanceMiddleware


def _tool(name):
    tool = MagicMock()
    tool.name = name
    return tool


def _list_tools_context(fastmcp_context):
    return MiddlewareContext(
        message=mcp_types.ListToolsRequest(),
        fastmcp_context=fastmcp_context,
        method="tools/list",
    )


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_on_list_tools_filters_by_lease(mock_fastmcp_context, lease_for_tool):
    """
    Ensure list_tools only includes bootstrap tools and leased tools.
    """
    await lease_for_tool("read_file", client_id=mock_fastmcp_context.session_id)

    tools = [
        _tool(name) for name in ["search_tools", "get_tool_schema", "read_file", "write_file"]
    ]
    middleware = GovernanceMiddleware()

    visible = await middleware.on_list_tools(
        _list_tools_context(mock_fastmcp_context), AsyncMock(return_value=tools)
    )

    visible_names = {tool.name for tool in visible}
    assert "search_tools" in visible_names
    assert "get_tool_schema" in visible_names
    assert "read_file" in visible_names
    assert "write_file" not in visible_names


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_on_list_tools_excludes_expired_leases(mock_fastmcp_context, lease_for_tool):
    """
    Ensure expired leases do not grant visibility.
    """
    await lease_for_tool("read_file", ttl=1, client_id=mock_fastmcp_context.session_id)
    await asyncio.sleep(2)

    tools = [_tool(name) for name in ["search_tools", "get_tool_schema", "read_file"]]
    middleware = GovernanceMiddleware()

    visible = await middleware.on_list_tools(
        _list_tools_context(mock_fastmcp_context), AsyncMock(return_value=tools)
    )

    assert "read_file" not in {tool.name for tool in visible}


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_on_list_tools_scoped_to_client(mock_fastmcp_context, lease_for_tool):
    """
    Ensure leases do not grant visibility to other clients.
    """
    await lease_for_tool("write_file", client_id="client-a")

    mock_fastmcp_context.session_id = "client-b"
    tools = [_tool(name) for name in ["search_tools", "get_tool_schema", "write_file"]]
    middleware = GovernanceMiddleware()

    visible = await middleware.on_list_tools(
        _list_tools_context(mock_fastmcp_context), AsyncMock(return_value=tools)
    )

    assert "write_file" not in {tool.name for tool in visible}
