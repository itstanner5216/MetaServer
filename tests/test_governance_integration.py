"""
Integration Tests for Governance + Leases (Phase 3 + 4)

These tests verify the interaction between:
- Governance policy engine (Phase 4)
- Lease manager (Phase 3)
- Tool visibility (Progressive Discovery)

Test Scenarios:
1. Governance check happens BEFORE lease grant
2. Capability tokens are verified at tool CALL time
3. READ_ONLY mode blocks all sensitive tools
4. Mode changes affect lease grants but not existing leases
"""

import json
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from src.meta_mcp.config import Config
from src.meta_mcp.governance.tokens import verify_token
from src.meta_mcp.leases import lease_manager
from src.meta_mcp.registry import tool_registry
from src.meta_mcp.state import ExecutionMode, governance_state
from src.meta_mcp.supervisor import get_tool_schema


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_governance_check_before_lease_grant(
    redis_client, governance_in_read_only, mock_fastmcp_context
):
    """
    Verify governance check happens BEFORE lease is granted.

    Flow:
    1. Call get_tool_schema("write_file")
    2. Governance checks mode and tool sensitivity
    3. If blocked, deny without granting lease
    4. If allowed, grant lease then return schema

    This prevents granting leases for tools that will be blocked anyway.
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Attempt to get schema for write_file (blocked in READ_ONLY)
    with pytest.raises(ToolError, match="blocked"):
        await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)

    # Verify NO lease was granted
    lease = await lease_manager.validate(client_id, "write_file")
    assert lease is None, "Should not grant lease for blocked tool"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_token_verification_at_call_time(redis_client, governance_in_bypass, mock_fastmcp_context):
    """
    Verify capability tokens are verified at tool CALL time, not just grant time.

    Flow:
    1. get_tool_schema grants a lease with token
    2. Lease stores the capability token
    3. Token can be verified during tool invocation
    """
    client_id = "test_session"
    mock_fastmcp_context.session_id = client_id

    # Get schema (should grant lease in BYPASS)
    response = await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "write_file"

    # Verify lease was granted
    lease = await lease_manager.validate(client_id, "write_file")
    assert lease is not None
    assert lease.capability_token is not None

    # Verify token matches lease binding
    assert verify_token(
        token=lease.capability_token,
        client_id=client_id,
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_read_only_mode_blocks_sensitive_tools(
    redis_client, governance_in_read_only, mock_fastmcp_context
):
    """
    Verify READ_ONLY mode blocks all sensitive tools.

    Sensitive tools: write_file, delete_file, execute_command, etc.
    Safe tools: read_file, list_files, search_tools, etc.
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Get all registered tools
    all_tools = tool_registry.get_all_summaries()

    # Test each tool
    for tool in all_tools:
        if tool.risk_level != "safe":
            with pytest.raises(ToolError, match="blocked"):
                await get_tool_schema.fn(tool_name=tool.tool_id, ctx=mock_fastmcp_context)
        else:
            response = await get_tool_schema.fn(tool_name=tool.tool_id, ctx=mock_fastmcp_context)
            assert json.loads(response)["name"] == tool.tool_id


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_bypass_mode_skips_governance(
    redis_client, governance_in_bypass, mock_fastmcp_context
):
    """
    Verify BYPASS mode grants leases without governance checks.

    In BYPASS mode:
    - No approval required
    - All tools accessible
    - Leases granted immediately
    - No capability tokens needed
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Request schema for sensitive tool (no token needed)
    response = await get_tool_schema.fn(tool_name="delete_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "delete_file"

    # Verify lease was granted
    lease = await lease_manager.validate(client_id, "delete_file")
    assert lease is not None
    assert lease.mode_at_issue == ExecutionMode.BYPASS.value


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_mode_change_affects_new_lease_grants(
    redis_client, governance_in_permission, mock_fastmcp_context
):
    """
    Verify mode changes affect NEW lease grants.

    Flow:
    1. Mode is PERMISSION
    2. Get schema for write_file (requires approval)
    3. Change mode to BYPASS
    4. Get schema for delete_file (no approval needed)
    5. Verify second request succeeded without approval
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Request schema for write_file
    with pytest.raises(ToolError, match="requires approval"):
        await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)

    # Change mode to BYPASS
    await governance_state.set_mode(ExecutionMode.BYPASS)

    # Request schema for delete_file
    response = await get_tool_schema.fn(tool_name="delete_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "delete_file"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_existing_leases_remain_valid_after_mode_change(
    redis_client, governance_in_bypass, mock_fastmcp_context
):
    """
    Verify existing leases remain valid after mode change.

    Current design decision: Leases granted in one mode remain
    valid even if mode changes. They expire based on TTL only.

    Alternative design: Revoke all leases on mode change.
    This test documents the chosen behavior.
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Grant lease for write_file
    response = await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "write_file"

    # Verify lease exists
    lease = await lease_manager.validate(client_id, "write_file")
    assert lease is not None

    # Change mode to READ_ONLY
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Verify lease still valid
    lease_check = await lease_manager.validate(client_id, "write_file")
    assert lease_check is not None, "Existing leases should remain valid after mode change"

    # Note: Tool CALL might still be blocked by middleware governance check
    # This test only verifies lease validity, not tool execution permission


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_policy_matrix_integration(
    redis_client, governance_in_permission, mock_fastmcp_context
):
    """
    Verify governance policy matrix correctly gates lease grants.

    Policy Matrix (Phase 4):
    - READ_ONLY + safe tool = allow
    - READ_ONLY + sensitive tool = block
    - PERMISSION + safe tool = allow
    - PERMISSION + sensitive tool = require_approval
    - BYPASS + any tool = allow
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Test READ_ONLY + safe
    await governance_state.set_mode(ExecutionMode.READ_ONLY)
    response = await get_tool_schema.fn(tool_name="read_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "read_file"

    # Test READ_ONLY + sensitive
    with pytest.raises(ToolError, match="blocked"):
        await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)

    # Test PERMISSION + safe
    await governance_state.set_mode(ExecutionMode.PERMISSION)
    response = await get_tool_schema.fn(tool_name="read_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "read_file"

    # Test PERMISSION + sensitive
    with pytest.raises(ToolError, match="requires approval"):
        await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)

    # Test BYPASS + any
    await governance_state.set_mode(ExecutionMode.BYPASS)
    response = await get_tool_schema.fn(tool_name="delete_file", ctx=mock_fastmcp_context)
    assert json.loads(response)["name"] == "delete_file"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_lease_ttl_based_on_risk_level(
    redis_client, governance_in_bypass, mock_fastmcp_context
):
    """
    Verify lease TTL is based on tool risk level.

    From Config (Phase 0):
    - safe tools: 300s, 3 calls
    - sensitive tools: 300s, 1 call
    - dangerous tools: 120s, 1 call
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Grant lease for safe tool
    await get_tool_schema.fn(tool_name="read_file", ctx=mock_fastmcp_context)
    lease_safe = await lease_manager.validate(client_id, "read_file")
    assert lease_safe.calls_remaining == Config.LEASE_CALLS_BY_RISK["safe"]

    # Grant lease for sensitive tool
    await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)
    lease_sensitive = await lease_manager.validate(client_id, "write_file")
    assert lease_sensitive.calls_remaining == Config.LEASE_CALLS_BY_RISK["sensitive"]


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_governance_fail_safe_on_redis_error(redis_client, mock_fastmcp_context):
    """
    Verify governance fails safe when Redis is unavailable.

    Expected behavior:
    - get_mode() returns PERMISSION (fail-safe default)
    - Lease validation fails closed (returns None)
    - All tool access requires approval or is denied
    """
    client_id = "test_client_id"
    mock_fastmcp_context.session_id = client_id

    # Mock Redis to fail
    with patch("src.meta_mcp.state.governance_state._get_redis") as mock_redis:
        mock_redis.side_effect = Exception("Redis connection failed")

        # Verify mode defaults to PERMISSION
        mode = await governance_state.get_mode()
        assert mode == ExecutionMode.PERMISSION, "Should fail-safe to PERMISSION"

        # Attempt to get schema
        with pytest.raises(ToolError, match="requires approval"):
            await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_token_required_in_permission_mode(redis_client, governance_in_permission, mock_fastmcp_context):
    """
    Verify capability token is required for sensitive tools in PERMISSION mode.

    Flow:
    1. Mode is PERMISSION
    2. Request schema for write_file without token
    3. Should get approval-required response
    """
    client_id = "test_session"
    mock_fastmcp_context.session_id = client_id

    # Request without token
    with pytest.raises(ToolError, match="requires approval"):
        await get_tool_schema.fn(tool_name="write_file", ctx=mock_fastmcp_context)

    # Verify no lease was granted
    lease = await lease_manager.validate(client_id, "write_file")
    assert lease is None
