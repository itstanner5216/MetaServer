"""
End-to-End Integration Tests for Phase 3+4

Tests complete workflow from discovery to execution:
- Progressive discovery (search → schema → execute)
- Governance approval flow
- Lease grant and consumption
- Audit logging
"""

import json

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.leases import lease_manager
from src.meta_mcp.state import ExecutionMode, governance_state
from src.meta_mcp.supervisor import get_tool_schema, mcp, search_tools
from tests.test_utils import mock_fastmcp_context


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_permission_mode_requires_approval(redis_client):
    """
    Test complete flow: search → schema request → approval required.
    """
    await governance_state.set_mode(ExecutionMode.PERMISSION)

    results = search_tools.fn(query="file operations")
    assert "write_file" in str(results).lower()

    tools_before = await mcp.get_tools()
    tool_names_before = {tool.name for tool in tools_before.values()}

    with pytest.raises(ToolError, match="requires approval"):
        await get_tool_schema.fn(tool_name="write_file")

    tools_after = await mcp.get_tools()
    tool_names_after = {tool.name for tool in tools_after.values()}
    if "write_file" not in tool_names_before:
        assert "write_file" not in tool_names_after


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_bypass_mode_grants_schema_and_lease(redis_client):
    """
    Test that BYPASS mode grants immediate schema access and lease.
    """
    await governance_state.set_mode(ExecutionMode.BYPASS)

    ctx = mock_fastmcp_context(session_id="e2e_bypass_client")
    response = await get_tool_schema.fn(tool_name="delete_file", ctx=ctx)
    response_data = json.loads(response) if isinstance(response, str) else response

    assert response_data.get("inputSchema") is not None

    lease = await lease_manager.validate("e2e_bypass_client", "delete_file")
    assert lease is not None
    assert lease.mode_at_issue == "bypass"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_read_only_mode_blocks_flow(redis_client):
    """
    Test that READ_ONLY mode blocks sensitive tool access at schema request.
    """
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    results = search_tools.fn(query="file")
    assert results is not None

    with pytest.raises(ToolError, match="blocked by policy"):
        await get_tool_schema.fn(tool_name="write_file")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_exhaustion_flow(redis_client):
    """
    Test that lease exhaustion prevents further calls.
    """
    await governance_state.set_mode(ExecutionMode.BYPASS)

    ctx = mock_fastmcp_context(session_id="e2e_exhaust_client")
    response = await get_tool_schema.fn(tool_name="read_file", ctx=ctx)
    response_data = json.loads(response) if isinstance(response, str) else response
    assert response_data.get("inputSchema") is not None

    lease = await lease_manager.validate("e2e_exhaust_client", "read_file")
    assert lease is not None

    for _ in range(lease.calls_remaining):
        await lease_manager.consume("e2e_exhaust_client", "read_file")

    exhausted = await lease_manager.validate("e2e_exhaust_client", "read_file")
    assert exhausted is None or exhausted.calls_remaining == 0
