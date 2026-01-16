"""Tests for tool visibility filtering in list_tools."""

import asyncio

import pytest

from src.meta_mcp.middleware import GovernanceMiddleware


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_on_list_tools_filters_by_lease(mock_fastmcp_context, lease_for_tool):
    """
    Ensure list_tools only includes bootstrap tools and leased tools.
    """
    await lease_for_tool("read_file", client_id=mock_fastmcp_context.session_id)

    tools = ["search_tools", "get_tool_schema", "read_file", "write_file"]
    middleware = GovernanceMiddleware()

    visible = await middleware.on_list_tools(tools, mock_fastmcp_context)

    assert "search_tools" in visible
    assert "get_tool_schema" in visible
    assert "read_file" in visible
    assert "write_file" not in visible


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_on_list_tools_excludes_expired_leases(mock_fastmcp_context, lease_for_tool):
    """
    Ensure expired leases do not grant visibility.
    """
    await lease_for_tool("read_file", ttl=1, client_id=mock_fastmcp_context.session_id)
    await asyncio.sleep(2)

    tools = ["search_tools", "get_tool_schema", "read_file"]
    middleware = GovernanceMiddleware()

    visible = await middleware.on_list_tools(tools, mock_fastmcp_context)

    assert "read_file" not in visible


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_on_list_tools_scoped_to_client(mock_fastmcp_context, lease_for_tool):
    """
    Ensure leases do not grant visibility to other clients.
    """
    await lease_for_tool("write_file", client_id="client-a")

    mock_fastmcp_context.session_id = "client-b"
    tools = ["search_tools", "get_tool_schema", "write_file"]
    middleware = GovernanceMiddleware()

    visible = await middleware.on_list_tools(tools, mock_fastmcp_context)

    assert "write_file" not in visible
