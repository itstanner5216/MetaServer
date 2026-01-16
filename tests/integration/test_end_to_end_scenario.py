"""
Integration Tests: Complete End-to-End Scenarios

Tests complete workflows spanning all phases:
1. Complete workflow from search to execution
2. Mode transitions (READ_ONLY -> PERMISSION -> BYPASS)
3. Lease lifecycle with notifications
4. Governance enforcement throughout

This is the most comprehensive integration test suite,
verifying all phases work together correctly.
"""

import asyncio

import pytest
from src.meta_mcp.config import Config
from src.meta_mcp.registry import tool_registry
from src.meta_mcp.governance.policy import evaluate_policy
from src.meta_mcp.governance.tokens import generate_token, verify_token
from src.meta_mcp.leases.manager import lease_manager
from src.meta_mcp.macros.batch_read import batch_read_tools
from src.meta_mcp.macros.batch_search import batch_search_tools
from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.state import ExecutionMode, governance_state
from src.meta_mcp.toon.encoder import encode_output


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_complete_safe_tool_workflow(redis_client):
    """
    End-to-end workflow for safe tool (no approval needed).

    Flow:
    1. Client searches for "read" tools
    2. Finds read_file in results
    3. Requests schema (no approval needed - safe tool)
    4. Tool becomes available
    5. Client uses tool
    6. No lease needed (safe tool in any mode)
    """
    # Step 1: Search
    results = tool_registry.search("read")
    assert len(results) > 0

    # Step 2: Find read_file (use canonical tool_id instead of compatibility name)
    read_file = next((t for t in results if t.tool_id == "read_file"), None)
    assert read_file is not None
    assert read_file.sensitive is False  # Safe tool

    # Step 3: Policy check (should allow)
    decision = evaluate_policy(mode=ExecutionMode.PERMISSION, tool_risk="safe", tool_id="read_file")
    assert decision.action == "allow"
    assert not decision.requires_approval

    # Step 4: Tool available without lease (safe tools don't need leases)
    # In real implementation, safe tools are always accessible

    # Step 5: Tool execution would happen here
    # Safe tools execute without governance checks


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_complete_sensitive_tool_workflow(redis_client):
    """
    End-to-end workflow for sensitive tool (requires approval).

    Flow:
    1. Client searches for "write" tools
    2. Finds write_file in results
    3. Requests schema
    4. Governance requires approval (PERMISSION mode)
    5. User approves -> capability token generated
    6. Lease granted with token
    7. Client calls tool
    8. Token verified, lease consumed
    9. Tool executes successfully
    """
    # Step 1: Search
    results = tool_registry.search("write")
    assert len(results) > 0

    # Step 2: Find write_file (use canonical tool_id instead of compatibility name)
    write_file = next((t for t in results if t.tool_id == "write_file"), None)
    assert write_file is not None
    assert write_file.sensitive is True  # Sensitive tool

    # Step 3: Policy check (requires approval)
    decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="sensitive", tool_id="write_file"
    )
    assert decision.action == "require_approval"
    assert decision.requires_approval

    # Step 4: User approves (simulate)
    token = generate_token(
        client_id="sensitive_workflow_test",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )
    assert token is not None

    # Step 5: Grant lease with token
    lease = await lease_manager.grant(
        client_id="sensitive_workflow_test",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
        capability_token=token,
    )
    assert lease is not None
    assert lease.capability_token == token

    # Step 6: Verify token
    valid = verify_token(
        token=lease.capability_token,
        client_id="sensitive_workflow_test",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid is True

    # Step 7: Consume lease (tool execution)
    consumed = await lease_manager.consume("sensitive_workflow_test", "write_file")
    assert consumed.calls_remaining == 2

    # Step 8: Tool executes successfully
    # (actual execution would happen in middleware)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_mode_transition_read_only_to_permission(redis_client):
    """
    Test mode transition from READ_ONLY to PERMISSION.

    Flow:
    1. Start in READ_ONLY mode
    2. Sensitive tool blocked
    3. Transition to PERMISSION mode
    4. Same tool now requires approval
    5. Existing leases unaffected
    """
    # Step 1: Set READ_ONLY mode
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Step 2: Check sensitive tool (blocked)
    decision = evaluate_policy(
        mode=ExecutionMode.READ_ONLY, tool_risk="sensitive", tool_id="write_file"
    )
    assert decision.action == "block"

    # Grant a safe tool lease in READ_ONLY
    safe_lease = await lease_manager.grant(
        client_id="mode_transition_test",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="READ_ONLY",
    )
    assert safe_lease is not None

    # Step 3: Transition to PERMISSION
    await governance_state.set_mode(ExecutionMode.PERMISSION)

    # Step 4: Check same tool (now requires approval)
    decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="sensitive", tool_id="write_file"
    )
    assert decision.action == "require_approval"

    # Step 5: Existing lease unaffected
    validated = await lease_manager.validate("mode_transition_test", "read_file")
    assert validated is not None
    assert validated.mode_at_issue == "READ_ONLY"  # Captured at grant time


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_mode_transition_permission_to_bypass(redis_client):
    """
    Test mode transition from PERMISSION to BYPASS.

    Flow:
    1. Start in PERMISSION mode
    2. Sensitive tool requires approval
    3. Transition to BYPASS mode
    4. Same tool now allowed without approval
    """
    # Step 1: Set PERMISSION mode
    await governance_state.set_mode(ExecutionMode.PERMISSION)

    # Step 2: Sensitive tool requires approval
    decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="dangerous", tool_id="execute_command"
    )
    assert decision.action == "require_approval"

    # Step 3: Transition to BYPASS
    await governance_state.set_mode(ExecutionMode.BYPASS)

    # Step 4: Same tool now allowed
    decision = evaluate_policy(
        mode=ExecutionMode.BYPASS, tool_risk="dangerous", tool_id="execute_command"
    )
    assert decision.action == "allow"
    assert not decision.requires_approval


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_lifecycle_with_notifications(redis_client):
    """
    Test complete lease lifecycle with notifications.

    Flow:
    1. Register notification callback
    2. Grant lease -> notification
    3. Consume lease -> tool execution
    4. Exhaust lease -> notification
    5. Tool no longer available
    """
    # Step 1: Register callback
    notifications = []

    async def notification_callback(client_id):
        notifications.append(("list_changed", client_id))

    lease_manager.register_notification_callback(notification_callback)

    try:
        # Step 2: Grant lease
        lease = await lease_manager.grant(
            client_id="lifecycle_test",
            tool_id="write_file",
            ttl_seconds=300,
            calls_remaining=2,
            mode_at_issue="PERMISSION",
        )
        assert lease is not None

        assert len(notifications) == 1

        # Step 3: Consume lease
        consumed = await lease_manager.consume("lifecycle_test", "write_file")
        assert consumed.calls_remaining == 1

        # Step 4: Exhaust lease
        consumed = await lease_manager.consume("lifecycle_test", "write_file")
        assert consumed.calls_remaining == 0

        assert len(notifications) == 2

        # Step 5: Tool no longer available
        validated = await lease_manager.validate("lifecycle_test", "write_file")
        assert validated is None

    finally:
        lease_manager.unregister_notification_callback(notification_callback)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_progressive_discovery_with_toon_encoding(redis_client):
    """
    Test progressive discovery with TOON encoding for large results.

    Flow:
    1. Search returns many tools
    2. Results compressed via TOON
    3. Client requests specific tool schema
    4. Full schema returned
    5. Tool becomes available
    """
    # Step 1: Search for broad query
    results = tool_registry.search("file")
    assert len(results) > 0

    # Step 2: Simulate large result set
    large_results = {"tools": [{"name": f"tool_{i}", "desc": "Tool"} for i in range(50)]}
    encoded = encode_output(large_results, threshold=10)

    # Verify TOON compression
    assert "__toon" in encoded["tools"]
    assert encoded["tools"]["count"] == 50
    assert len(encoded["tools"]["sample"]) == 3

    # Step 3: Request specific tool (no TOON needed for single tool)
    single_tool = {"name": "read_file", "schema": {"type": "object"}}
    encoded_single = encode_output(single_tool, threshold=10)

    # No compression for single object
    assert "__toon" not in str(encoded_single)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_batch_operations_with_governance(redis_client, fresh_registry):
    """
    Test batch operations respect governance policies.

    Flow:
    1. Create registry with mixed risk tools
    2. Batch search finds all tools
    3. Batch read with risk filtering
    4. Only approved risk levels returned
    """
    # Step 1: Create registry
    tool_specs = [
        ("safe_tool_1", "safe"),
        ("safe_tool_2", "safe"),
        ("sensitive_tool_1", "sensitive"),
        ("dangerous_tool_1", "dangerous"),
    ]

    registry = fresh_registry

    for tool_id, risk in tool_specs:
        registry.add_for_testing(
            ToolRecord(
                tool_id=tool_id,
                server_id="test_server",
                description_1line=f"{risk.capitalize()} tool",
                description_full=f"{risk.capitalize()} tool",
                tags=["test"],
                risk_level=risk,
            )
        )

    # Step 2: Batch search
    search_results = batch_search_tools(registry=registry, queries=["tool"])
    assert len(search_results["tool"]) == 4

    # Step 3: Batch search with risk exclusion
    filtered_search = batch_search_tools(
        registry=registry, queries=["tool"], exclude_risk_levels=["dangerous"]
    )
    assert all(c.risk_level != "dangerous" for c in filtered_search["tool"])

    # Step 4: Batch read with risk filtering
    all_ids = [tid for tid, _ in tool_specs]
    safe_only = batch_read_tools(registry=registry, tool_ids=all_ids, max_risk_level="safe")

    assert safe_only["safe_tool_1"] is not None
    assert safe_only["safe_tool_2"] is not None
    assert safe_only["sensitive_tool_1"] is None
    assert safe_only["dangerous_tool_1"] is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_multi_client_isolation(redis_client):
    """
    Test that multiple clients are properly isolated.

    Flow:
    1. Client A grants lease for tool X
    2. Client B cannot access Client A's lease
    3. Client B grants own lease for tool X
    4. Both leases coexist independently
    5. Each client can only consume their own lease
    """
    # Step 1: Client A grants lease
    lease_a = await lease_manager.grant(
        client_id="client_a",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )
    assert lease_a is not None

    # Step 2: Client B cannot access Client A's lease
    lease_b_check = await lease_manager.validate("client_b", "write_file")
    assert lease_b_check is None

    # Step 3: Client B grants own lease
    lease_b = await lease_manager.grant(
        client_id="client_b",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease_b is not None

    # Step 4: Both leases exist
    lease_a_check = await lease_manager.validate("client_a", "write_file")
    lease_b_check = await lease_manager.validate("client_b", "write_file")
    assert lease_a_check is not None
    assert lease_b_check is not None

    # Step 5: Each client consumes their own lease
    consumed_a = await lease_manager.consume("client_a", "write_file")
    assert consumed_a.calls_remaining == 2

    consumed_b = await lease_manager.consume("client_b", "write_file")
    assert consumed_b.calls_remaining == 4

    # Leases remain independent
    final_a = await lease_manager.validate("client_a", "write_file")
    final_b = await lease_manager.validate("client_b", "write_file")
    assert final_a.calls_remaining == 2
    assert final_b.calls_remaining == 4


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_token_forgery_prevention(redis_client):
    """
    Test that forged tokens are rejected.

    Security Invariant: Tokens cannot be tampered with.

    Flow:
    1. Generate valid token
    2. Modify token payload
    3. Verification fails
    4. Grant lease with forged token fails
    """
    # Step 1: Generate valid token
    valid_token = generate_token(
        client_id="forgery_test", tool_id="write_file", ttl_seconds=300, secret=Config.HMAC_SECRET
    )

    # Step 2: Forge token (modify payload)
    parts = valid_token.split(".")
    forged_token = parts[0] + "X." + parts[1]  # Corrupt payload

    # Step 3: Verification fails
    valid = verify_token(
        token=forged_token,
        client_id="forgery_test",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid is False

    # Also test signature tampering
    forged_sig = parts[0] + "." + parts[1] + "X"  # Corrupt signature
    valid = verify_token(
        token=forged_sig, client_id="forgery_test", tool_id="write_file", secret=Config.HMAC_SECRET
    )
    assert valid is False


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_complete_user_journey(redis_client):
    """
    Simulate complete user journey from start to finish.

    Journey:
    1. User starts session (READ_ONLY mode)
    2. Searches for tools to understand capabilities
    3. Finds safe tools, uses them freely
    4. Finds sensitive tool, blocked in READ_ONLY
    5. Admin elevates to PERMISSION mode
    6. User requests sensitive tool
    7. Approval prompt shown
    8. User approves
    9. Lease granted
    10. User executes tool multiple times
    11. Lease expires
    12. User must re-approve for more uses
    """
    # Step 1: Start in READ_ONLY
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Step 2: Search for tools
    results = tool_registry.search("file")
    assert len(results) > 0

    # Step 3: Safe tools accessible
    safe_decision = evaluate_policy(
        mode=ExecutionMode.READ_ONLY, tool_risk="safe", tool_id="read_file"
    )
    assert safe_decision.action == "allow"

    # Step 4: Sensitive tool blocked
    sensitive_decision = evaluate_policy(
        mode=ExecutionMode.READ_ONLY, tool_risk="sensitive", tool_id="write_file"
    )
    assert sensitive_decision.action == "block"

    # Step 5: Elevate to PERMISSION
    await governance_state.set_mode(ExecutionMode.PERMISSION)

    # Step 6: Request sensitive tool
    sensitive_decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="sensitive", tool_id="write_file"
    )
    assert sensitive_decision.action == "require_approval"

    # Step 7-8: User approves
    token = generate_token(
        client_id="user_journey_test",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    # Step 9: Grant lease
    lease = await lease_manager.grant(
        client_id="user_journey_test",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
        capability_token=token,
    )
    assert lease is not None

    # Step 10: Execute multiple times
    for expected_remaining in [2, 1, 0]:
        consumed = await lease_manager.consume("user_journey_test", "write_file")
        assert consumed.calls_remaining == expected_remaining

    # Step 11: Lease exhausted
    validated = await lease_manager.validate("user_journey_test", "write_file")
    assert validated is None

    # Step 12: Must re-approve (new lease needed)
    # User would go through approval flow again


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_security_invariants_maintained(redis_client, fresh_registry):
    """
    Verify critical security invariants across all phases.

    Invariants:
    1. Bootstrap tools always accessible
    2. Client isolation maintained
    3. Tokens cannot be forged
    4. Leases expire automatically
    5. Mode changes don't affect existing leases
    6. Risk filtering works correctly
    """
    # Invariant 1: Bootstrap tools always accessible
    for mode in [ExecutionMode.READ_ONLY, ExecutionMode.PERMISSION, ExecutionMode.BYPASS]:
        decision = evaluate_policy(mode, "safe", "search_tools")
        assert decision.action == "allow"

    # Invariant 2: Client isolation
    await lease_manager.grant("client_x", "tool_a", 300, 5, "PERMISSION")
    lease_y = await lease_manager.validate("client_y", "tool_a")
    assert lease_y is None

    # Invariant 3: Token forgery prevention
    token = generate_token("test", "tool", 300, Config.HMAC_SECRET)
    forged = token[:-5] + "xxxxx"
    assert not verify_token(forged, "test", "tool", Config.HMAC_SECRET)

    # Invariant 4: Automatic expiration
    await lease_manager.grant("expire_test", "tool_b", 1, 5, "PERMISSION")
    await asyncio.sleep(2)
    expired = await lease_manager.validate("expire_test", "tool_b")
    assert expired is None

    # Invariant 5: Mode changes don't affect existing leases
    await governance_state.set_mode(ExecutionMode.PERMISSION)
    lease = await lease_manager.grant("mode_test", "tool_c", 300, 5, "PERMISSION")
    await governance_state.set_mode(ExecutionMode.READ_ONLY)
    validated = await lease_manager.validate("mode_test", "tool_c")
    assert validated is not None
    assert validated.mode_at_issue == "PERMISSION"

    # Invariant 6: Risk filtering
    registry = fresh_registry
    registry.add_for_testing(
        ToolRecord(
            tool_id="safe",
            server_id="test_server",
            description_1line="Safe",
            description_full="Safe",
            tags=["test"],
            risk_level="safe",
        )
    )
    registry.add_for_testing(
        ToolRecord(
            tool_id="dangerous",
            server_id="test_server",
            description_1line="Dangerous",
            description_full="Dangerous",
            tags=["test"],
            risk_level="dangerous",
        )
    )

    results = batch_read_tools(registry, ["safe", "dangerous"], max_risk_level="safe")
    assert results["safe"] is not None
    assert results["dangerous"] is None
