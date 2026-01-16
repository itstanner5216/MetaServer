"""
CRITICAL Security Tests for Schema Leakage Prevention (Phase 4)

These tests ensure that tool schemas are not leaked before authorization.

Schema leakage allows attackers to:
- Analyze tool capabilities without permission
- Understand tool arguments before governance approval
- Probe for sensitive functionality even in READ_ONLY mode

Security Requirements:
1. Blocked tools must NOT return schema
2. approval_required response must NOT include schema
3. Schema only returned when lease is successfully granted
"""

import json

import pytest

from fastmcp.exceptions import ToolError

from src.meta_mcp.config import Config
from src.meta_mcp.leases import lease_manager
from src.meta_mcp.supervisor import get_tool_schema, mcp, search_tools, tool_registry
from tests.test_utils import assert_audit_log_contains, mock_fastmcp_context


pytestmark = pytest.mark.requires_redis


def _parse_schema_response(response: str | dict) -> dict:
    if isinstance(response, str):
        return json.loads(response)
    return response


def _tool_names(tools: dict) -> set[str]:
    return {tool.name for tool in tools.values()}


@pytest.mark.asyncio
async def test_blocked_tool_schema_not_exposed(
    audit_log_path, redis_client, governance_in_read_only
):
    """
    Blocked tools should not expose schemas.

    Per design Section 7.1: "Governance is enforced at schema exposure time.
    A blocked tool never has its schema revealed."
    """
    tools_before = await mcp.get_tools()
    tool_names_before = _tool_names(tools_before)

    with pytest.raises(ToolError, match="blocked"):
        await get_tool_schema.fn(tool_name="write_file")

    tools_after = await mcp.get_tools()
    tool_names_after = _tool_names(tools_after)
    assert tool_names_after == tool_names_before

    if audit_log_path.exists() and audit_log_path.read_text().strip():
        await assert_audit_log_contains(
            "blocked_read_only",
            tool_name="write_file",
        )


@pytest.mark.asyncio
async def test_blocked_tool_never_appears_in_list_tools(
    redis_client, governance_in_read_only
):
    """
    SECURITY: Verify blocked tools never exposed to tools/list.
    """
    tools_before = await mcp.get_tools()
    before_names = _tool_names(tools_before)

    with pytest.raises(ToolError, match="blocked"):
        await get_tool_schema.fn(tool_name="write_file")

    tools_after = await mcp.get_tools()
    after_names = _tool_names(tools_after)

    assert after_names == before_names


@pytest.mark.asyncio
async def test_approval_required_no_schema(redis_client, governance_in_permission):
    """
    CRITICAL: approval_required response must NOT include schema.
    """
    tools_before = await mcp.get_tools()
    before_names = _tool_names(tools_before)

    with pytest.raises(ToolError) as excinfo:
        await get_tool_schema.fn(tool_name="write_file")

    error_msg = str(excinfo.value)
    assert "inputschema" not in error_msg.lower()
    assert "properties" not in error_msg.lower()

    tools_after = await mcp.get_tools()
    after_names = _tool_names(tools_after)
    assert after_names == before_names


@pytest.mark.asyncio
async def test_schema_only_after_lease_grant(redis_client, governance_in_bypass):
    """
    Verify schema is ONLY returned when lease is successfully granted.
    """
    ctx = mock_fastmcp_context(session_id="schema_grant_client")
    response = await get_tool_schema.fn(tool_name="read_file", ctx=ctx)
    response_data = _parse_schema_response(response)

    assert response_data.get("inputSchema") is not None

    lease = await lease_manager.validate("schema_grant_client", "read_file")
    assert lease is not None, "Lease should be created when schema returned"

    tools_after = await mcp.get_tools()
    assert "read_file" in _tool_names(tools_after)


@pytest.mark.asyncio
async def test_schema_minimal_before_expansion(redis_client, governance_in_bypass):
    """
    Verify schema sizing behavior based on progressive schema flag.
    """
    response = await get_tool_schema.fn(tool_name="read_file")
    response_data = _parse_schema_response(response)
    schema = response_data.get("inputSchema")

    assert schema is not None

    tool_record = tool_registry.get("read_file")
    if Config.ENABLE_PROGRESSIVE_SCHEMAS and tool_record and tool_record.schema_min:
        assert schema == tool_record.schema_min


@pytest.mark.asyncio
async def test_error_message_no_schema_leak(redis_client, governance_in_read_only):
    """
    Verify error messages don't leak schema information.
    """
    with pytest.raises(ToolError) as excinfo:
        await get_tool_schema.fn(tool_name="write_file")

    error_msg = str(excinfo.value).lower()
    assert "properties" not in error_msg
    assert "inputschema" not in error_msg
    assert "type" not in error_msg or "file" in error_msg


@pytest.mark.asyncio
async def test_search_results_no_schema(redis_client):
    """
    Verify search_tools response does not include schemas.
    """
    results = search_tools.fn(query="file")

    if isinstance(results, str):
        results_lower = results.lower()
        assert "inputschema" not in results_lower
        assert "properties" not in results_lower
    else:
        for result in results:
            assert "inputSchema" not in result
            assert "schema" not in result
            assert "properties" not in result


@pytest.mark.asyncio
async def test_bootstrap_tools_schema_always_available(
    redis_client, governance_in_read_only
):
    """
    Verify bootstrap tools always return schema (no governance check).
    """
    response = await get_tool_schema.fn(tool_name="search_tools")
    response_data = _parse_schema_response(response)

    assert response_data.get("inputSchema") is not None


@pytest.mark.asyncio
async def test_schema_stripped_from_denial_response(
    redis_client, governance_in_read_only
):
    """
    CRITICAL: Ensure denial responses don't accidentally include schema.
    """
    with pytest.raises(ToolError) as excinfo:
        await get_tool_schema.fn(tool_name="write_file")

    response_str = str(excinfo.value)

    forbidden_keywords = ["inputSchema", "properties", "required", "$schema"]
    for keyword in forbidden_keywords:
        assert keyword not in response_str


@pytest.mark.asyncio
async def test_partial_schema_leak_in_json(redis_client, governance_in_read_only):
    """
    CRITICAL: Check for partial schema leakage via JSON serialization.
    """
    with pytest.raises(ToolError) as excinfo:
        await get_tool_schema.fn(tool_name="delete_file")

    response_str = str(excinfo.value)
    assert "inputSchema" not in response_str
    assert "properties" not in response_str
    assert "$schema" not in response_str


@pytest.mark.asyncio
async def test_schema_not_in_logs(redis_client, governance_in_read_only, capsys):
    """
    Verify schemas are not logged in error/debug messages.
    """
    with pytest.raises(ToolError):
        await get_tool_schema.fn(tool_name="write_file")

    captured = capsys.readouterr()
    output = f"{captured.out}{captured.err}".lower()
    assert "inputschema" not in output
    assert "properties" not in output


@pytest.mark.asyncio
async def test_multiple_blocked_requests_dont_accumulate(
    redis_client, governance_in_read_only
):
    """
    Multiple blocked schema requests should not expose tools.
    """
    tools_before = await mcp.get_tools()
    count_before = len(tools_before)

    for _ in range(2):
        with pytest.raises(ToolError):
            await get_tool_schema.fn(tool_name="write_file")

    tools_after = await mcp.get_tools()
    assert len(tools_after) == count_before


@pytest.mark.asyncio
async def test_permission_mode_blocks_dangerous_without_approval_at_schema(
    redis_client, governance_in_permission
):
    """
    Permission mode should require approval for dangerous tools at schema time.
    """
    tools_before = await mcp.get_tools()

    with pytest.raises(ToolError, match="requires approval"):
        await get_tool_schema.fn(tool_name="execute_command")

    tools_after = await mcp.get_tools()
    assert _tool_names(tools_after) == _tool_names(tools_before)


@pytest.mark.asyncio
async def test_bypass_mode_allows_all_at_schema_time(
    redis_client, governance_in_bypass
):
    """
    BYPASS mode should allow schema access for dangerous tools.
    """
    tools_before = await mcp.get_tools()
    names_before = _tool_names(tools_before)

    response = await get_tool_schema.fn(tool_name="execute_command")
    response_data = _parse_schema_response(response)
    assert response_data.get("inputSchema") is not None

    tools_after = await mcp.get_tools()
    names_after = _tool_names(tools_after)
    assert "execute_command" in names_after
    if "execute_command" not in names_before:
        assert len(names_after) == len(names_before) + 1


@pytest.mark.asyncio
async def test_tool_exposure_idempotent_after_allow(
    redis_client, governance_in_bypass
):
    """
    Allowing schema access should not duplicate tool exposure.
    """
    await get_tool_schema.fn(tool_name="read_file")
    tools_after_first = await mcp.get_tools()
    count_first = len(tools_after_first)

    await get_tool_schema.fn(tool_name="read_file")
    tools_after_second = await mcp.get_tools()
    count_second = len(tools_after_second)

    assert count_first == count_second


@pytest.mark.asyncio
async def test_blocked_tool_does_not_grant_lease(
    redis_client, governance_in_read_only
):
    """
    Blocked schema requests should not grant leases.
    """
    ctx = mock_fastmcp_context(session_id="blocked_lease_client")
    with pytest.raises(ToolError):
        await get_tool_schema.fn(tool_name="write_file", ctx=ctx)

    lease = await lease_manager.validate("blocked_lease_client", "write_file")
    assert lease is None


@pytest.mark.asyncio
async def test_approval_required_does_not_grant_lease(
    redis_client, governance_in_permission
):
    """
    Approval-required schema requests should not grant leases.
    """
    ctx = mock_fastmcp_context(session_id="approval_lease_client")
    with pytest.raises(ToolError):
        await get_tool_schema.fn(tool_name="write_file", ctx=ctx)

    lease = await lease_manager.validate("approval_lease_client", "write_file")
    assert lease is None


@pytest.mark.asyncio
async def test_blocked_tool_error_message_mentions_policy(
    redis_client, governance_in_read_only
):
    """
    Blocked responses should mention policy to avoid silent exposure.
    """
    with pytest.raises(ToolError) as excinfo:
        await get_tool_schema.fn(tool_name="write_file")

    message = str(excinfo.value).lower()
    assert "blocked" in message
    assert "read_only" in message


@pytest.mark.asyncio
async def test_permission_required_error_message_mentions_approval(
    redis_client, governance_in_permission
):
    """
    Approval-required responses should mention approval requirement.
    """
    with pytest.raises(ToolError) as excinfo:
        await get_tool_schema.fn(tool_name="write_file")

    assert "requires approval" in str(excinfo.value)


@pytest.mark.asyncio
async def test_tool_list_unchanged_after_permission_error(
    redis_client, governance_in_permission
):
    """
    Tool list should remain unchanged after approval-required error.
    """
    tools_before = await mcp.get_tools()
    count_before = len(tools_before)

    with pytest.raises(ToolError):
        await get_tool_schema.fn(tool_name="write_file")

    tools_after = await mcp.get_tools()
    assert len(tools_after) == count_before


@pytest.mark.asyncio
async def test_schema_leakage_time_window_zero_seconds(
    redis_client, governance_in_read_only
):
    """
    Blocked requests should not briefly expose tools.
    """
    tools_before = await mcp.get_tools()
    names_before = _tool_names(tools_before)

    with pytest.raises(ToolError):
        await get_tool_schema.fn(tool_name="write_file")

    tools_after = await mcp.get_tools()
    names_after = _tool_names(tools_after)
    assert names_after == names_before
