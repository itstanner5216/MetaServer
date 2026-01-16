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
from typing import Any

import pytest
from loguru import logger

from fastmcp.exceptions import ToolError

from src.meta_mcp.config import Config
from src.meta_mcp.leases import lease_manager
from src.meta_mcp.supervisor import get_tool_schema, mcp, search_tools
from tests.test_utils import assert_audit_log_contains, mock_fastmcp_context

pytestmark = pytest.mark.requires_redis


def _parse_response(response: Any) -> dict[str, Any]:
    if isinstance(response, str):
        return json.loads(response)
    return response


def _assert_no_schema_keywords(text: str) -> None:
    lowered = text.lower()
    for keyword in ["inputschema", "properties", "\"type\": \"object\"", "\"$schema\""]:
        assert keyword not in lowered, f"SECURITY BREACH: Schema keyword '{keyword}' found"


@pytest.mark.asyncio
async def test_blocked_tool_schema_not_exposed(
    audit_log_path, redis_client, governance_in_read_only
):
    """
    Blocked tools should not expose schemas.

    Per design Section 7.1: "Governance is enforced at schema exposure time.
    A blocked tool never has its schema revealed."

    Requires: 01_CRITICAL_BUGS.md Task 4 completed (schema-time governance)
    """
    tools_before = await mcp.get_tools()
    tool_names_before = {tool.name for tool in tools_before.values()}

    with pytest.raises(ToolError, match="blocked") as exc_info:
        await get_tool_schema.fn(tool_name="write_file")
    _assert_no_schema_keywords(str(exc_info.value))

    tools_after = await mcp.get_tools()
    tool_names_after = {tool.name for tool in tools_after.values()}
    if "write_file" not in tool_names_before:
        assert "write_file" not in tool_names_after

    if audit_log_path.exists() and audit_log_path.read_text().strip():
        await assert_audit_log_contains(
            "blocked_read_only",
            tool_name="write_file",
        )


@pytest.mark.asyncio
async def test_approval_required_no_schema(redis_client, governance_in_permission):
    """
    CRITICAL: approval_required response must NOT include schema.

    Security Risk: Schema in approval request leaks tool structure
    before user approves.
    """
    with pytest.raises(ToolError, match="requires approval") as exc_info:
        await get_tool_schema.fn(tool_name="write_file")

    _assert_no_schema_keywords(str(exc_info.value))


@pytest.mark.asyncio
async def test_schema_only_after_lease_grant(redis_client, governance_in_bypass):
    """
    Verify schema is ONLY returned when lease is successfully granted.

    This is the positive test case: when authorization succeeds,
    schema should be included in response.
    """
    ctx = mock_fastmcp_context(session_id="schema_grant_client")
    response = await get_tool_schema.fn(tool_name="read_file", ctx=ctx)
    response_data = _parse_response(response)

    assert response_data.get("inputSchema") is not None

    lease = await lease_manager.validate("schema_grant_client", "read_file")
    assert lease is not None, "Lease should be created when schema returned"


@pytest.mark.asyncio
async def test_schema_minimal_before_expansion(redis_client, governance_in_bypass):
    """
    Verify schema_min is returned initially, not full schema.

    Phase 5 feature: Progressive schemas start with minimal version
    and expand on demand.

    This test ensures full schema is not leaked in initial response.
    """
    response = await get_tool_schema.fn(tool_name="write_file")
    response_data = _parse_response(response)
    schema = response_data.get("inputSchema") or response_data.get("schema")

    if Config.ENABLE_PROGRESSIVE_SCHEMAS:
        schema_str = json.dumps(schema)
        token_estimate = len(schema_str) / 4
        assert token_estimate < 200, f"Initial schema too large: ~{token_estimate} tokens"
    else:
        assert schema is not None


@pytest.mark.asyncio
async def test_error_message_no_schema_leak(redis_client, governance_in_read_only):
    """
    Verify error messages don't leak schema information.

    Even in error cases, schema details should not be exposed.
    """
    with pytest.raises(ToolError) as exc_info:
        await get_tool_schema.fn(tool_name="write_file")

    _assert_no_schema_keywords(str(exc_info.value))


@pytest.mark.asyncio
async def test_search_results_no_schema():
    """
    Verify search_tools response does not include schemas.

    search_tools should return metadata only (name, description, tags).
    Schemas are only revealed via get_tool_schema.
    """
    results = search_tools.fn(query="file")

    if isinstance(results, str):
        results_lower = results.lower()
        assert "inputschema" not in results_lower
        assert "properties:" not in results_lower
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

    Bootstrap tools (search_tools, get_tool_schema) should always
    be accessible regardless of governance mode.
    """
    response = await get_tool_schema.fn(tool_name="search_tools")
    response_data = _parse_response(response)

    assert response_data.get("inputSchema") is not None, "Bootstrap tools should return schema"


@pytest.mark.asyncio
async def test_schema_stripped_from_denial_response(
    redis_client, governance_in_read_only
):
    """
    CRITICAL: Ensure denial responses don't accidentally include schema.

    This tests the response construction code to verify schemas are
    explicitly stripped from denial/error responses.
    """
    with pytest.raises(ToolError) as exc_info:
        await get_tool_schema.fn(tool_name="write_file")

    _assert_no_schema_keywords(str(exc_info.value))


@pytest.mark.asyncio
async def test_partial_schema_leak_in_json(redis_client, governance_in_read_only):
    """
    CRITICAL: Check for partial schema leakage via JSON serialization.

    Sometimes schemas leak via nested JSON fields or error details.
    This test checks the entire response structure.
    """
    with pytest.raises(ToolError) as exc_info:
        await get_tool_schema.fn(tool_name="delete_file")

    _assert_no_schema_keywords(str(exc_info.value))


@pytest.mark.asyncio
async def test_schema_not_in_logs(redis_client, governance_in_read_only):
    """
    Verify schemas are not logged in error/debug messages.

    Even if schemas aren't returned to client, logging them could
    leak information through log aggregation systems.
    """
    messages: list[str] = []
    handler_id = logger.add(lambda msg: messages.append(msg), format="{message}")
    try:
        with pytest.raises(ToolError):
            await get_tool_schema.fn(tool_name="write_file")
    finally:
        logger.remove(handler_id)

    for message in messages:
        _assert_no_schema_keywords(message)
