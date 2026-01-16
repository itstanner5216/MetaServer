"""
Integration Tests: Lease + Governance Flow (Phase 3 + 4)

Tests the interaction between lease management and governance:
1. Policy evaluation for different modes (Phase 4)
2. Lease granted with capability token (Phase 3 + 4)
3. Lease consumed and tracked (Phase 3)
4. Lease expiration handled (Phase 3)

Security Invariants:
- Leases scoped to (client_id, tool_id) pairs
- Capability tokens prevent forgery
- Governance blocks before lease grant
- Mode changes don't affect existing leases
"""

import asyncio
import time

import pytest

from src.meta_mcp.config import Config
from src.meta_mcp.governance.policy import evaluate_policy
from src.meta_mcp.governance.tokens import generate_token, verify_token
from src.meta_mcp.leases.manager import lease_manager
from src.meta_mcp.state import ExecutionMode, governance_state


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_policy_evaluation_read_only_mode(redis_client):
    """
    Verify policy evaluation in READ_ONLY mode.

    Policy Matrix (READ_ONLY):
    - Safe tools: ALLOW
    - Sensitive tools: BLOCK
    - Dangerous tools: BLOCK
    """
    # Safe tool allowed
    decision = evaluate_policy(mode=ExecutionMode.READ_ONLY, tool_risk="safe", tool_id="read_file")
    assert decision.action == "allow"
    assert not decision.requires_approval

    # Sensitive tool blocked
    decision = evaluate_policy(
        mode=ExecutionMode.READ_ONLY, tool_risk="sensitive", tool_id="write_file"
    )
    assert decision.action == "block"
    assert not decision.requires_approval

    # Dangerous tool blocked
    decision = evaluate_policy(
        mode=ExecutionMode.READ_ONLY, tool_risk="dangerous", tool_id="execute_command"
    )
    assert decision.action == "block"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_policy_evaluation_permission_mode(redis_client):
    """
    Verify policy evaluation in PERMISSION mode.

    Policy Matrix (PERMISSION):
    - Safe tools: ALLOW
    - Sensitive tools: REQUIRE_APPROVAL
    - Dangerous tools: REQUIRE_APPROVAL
    """
    # Safe tool allowed
    decision = evaluate_policy(mode=ExecutionMode.PERMISSION, tool_risk="safe", tool_id="read_file")
    assert decision.action == "allow"
    assert not decision.requires_approval

    # Sensitive tool requires approval
    decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="sensitive", tool_id="write_file"
    )
    assert decision.action == "require_approval"
    assert decision.requires_approval

    # Dangerous tool requires approval
    decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="dangerous", tool_id="execute_command"
    )
    assert decision.action == "require_approval"
    assert decision.requires_approval


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_policy_evaluation_bypass_mode(redis_client):
    """
    Verify policy evaluation in BYPASS mode.

    Policy Matrix (BYPASS):
    - Safe tools: ALLOW
    - Sensitive tools: ALLOW
    - Dangerous tools: ALLOW
    """
    # All tools allowed in BYPASS mode
    for risk in ["safe", "sensitive", "dangerous"]:
        decision = evaluate_policy(mode=ExecutionMode.BYPASS, tool_risk=risk, tool_id="any_tool")
        assert decision.action == "allow"
        assert not decision.requires_approval


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_bootstrap_tools_always_allowed(redis_client):
    """
    Verify bootstrap tools are always allowed regardless of mode.

    Security: search_tools and get_tool_schema must always work.
    """
    for mode in [ExecutionMode.READ_ONLY, ExecutionMode.PERMISSION, ExecutionMode.BYPASS]:
        # search_tools always allowed
        decision = evaluate_policy(mode=mode, tool_risk="safe", tool_id="search_tools")
        assert decision.action == "allow"

        # get_tool_schema always allowed
        decision = evaluate_policy(mode=mode, tool_risk="safe", tool_id="get_tool_schema")
        assert decision.action == "allow"

        # expand_tool_schema always allowed (Phase 5)
        decision = evaluate_policy(mode=mode, tool_risk="safe", tool_id="expand_tool_schema")
        assert decision.action == "allow"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_grant_and_validate(redis_client):
    """
    Verify lease can be granted and validated.

    Flow:
    1. Grant lease for client + tool
    2. Validate returns the lease
    3. Lease has correct properties
    """
    # Grant lease
    lease = await lease_manager.grant(
        client_id="test_session_123",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    assert lease is not None
    assert lease.client_id == "test_session_123"
    assert lease.tool_id == "read_file"
    assert lease.calls_remaining == 5
    assert lease.mode_at_issue == "PERMISSION"

    # Validate lease
    validated = await lease_manager.validate("test_session_123", "read_file")
    assert validated is not None
    assert validated.calls_remaining == 5


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_scoped_to_client_and_tool(redis_client):
    """
    Verify leases are scoped to (client_id, tool_id) pairs.

    Security: Client A cannot use lease granted to Client B.
    """
    # Grant lease to client A
    lease_a = await lease_manager.grant(
        client_id="client_a",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )
    assert lease_a is not None

    # Client B cannot access client A's lease
    lease_b = await lease_manager.validate("client_b", "write_file")
    assert lease_b is None

    # Client A can access their own lease
    lease_a_check = await lease_manager.validate("client_a", "write_file")
    assert lease_a_check is not None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_consume_decrements_calls(redis_client):
    """
    Verify lease consumption decrements calls_remaining.

    Flow:
    1. Grant lease with 3 calls
    2. Consume once -> 2 calls remaining
    3. Consume again -> 1 call remaining
    4. Consume final -> 0 calls, lease deleted
    """
    # Grant lease
    await lease_manager.grant(
        client_id="consumer_test",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="PERMISSION",
    )

    # Consume first call
    lease = await lease_manager.consume("consumer_test", "read_file")
    assert lease.calls_remaining == 2

    # Consume second call
    lease = await lease_manager.consume("consumer_test", "read_file")
    assert lease.calls_remaining == 1

    # Consume third call (exhausted)
    lease = await lease_manager.consume("consumer_test", "read_file")
    assert lease.calls_remaining == 0

    # Lease should be deleted after exhaustion
    validated = await lease_manager.validate("consumer_test", "read_file")
    assert validated is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_expiration_via_ttl(redis_client):
    """
    Verify leases expire automatically via Redis TTL.

    Flow:
    1. Grant lease with 1 second TTL
    2. Wait 2 seconds
    3. Lease should be expired/deleted
    """
    # Grant lease with short TTL
    lease = await lease_manager.grant(
        client_id="expire_test",
        tool_id="read_file",
        ttl_seconds=1,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None

    # Immediate validation should succeed
    validated = await lease_manager.validate("expire_test", "read_file")
    assert validated is not None

    # Wait for expiration
    await asyncio.sleep(2)

    # Lease should be expired
    expired = await lease_manager.validate("expire_test", "read_file")
    assert expired is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_revocation(redis_client):
    """
    Verify leases can be manually revoked.

    Flow:
    1. Grant lease
    2. Revoke lease
    3. Validate returns None
    """
    # Grant lease
    await lease_manager.grant(
        client_id="revoke_test",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )

    # Verify lease exists
    lease = await lease_manager.validate("revoke_test", "write_file")
    assert lease is not None

    # Revoke lease
    revoked = await lease_manager.revoke("revoke_test", "write_file")
    assert revoked is True

    # Lease should be gone
    validated = await lease_manager.validate("revoke_test", "write_file")
    assert validated is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_capability_token_generation_and_verification(redis_client):
    """
    Verify capability tokens can be generated and verified.

    Flow:
    1. Generate token for client + tool
    2. Verify token with correct parameters
    3. Reject token with wrong parameters
    """
    # Generate token
    token = generate_token(
        client_id="token_test", tool_id="write_file", ttl_seconds=300, secret=Config.HMAC_SECRET
    )

    assert token is not None
    assert "." in token  # Format: payload.signature

    # Verify with correct parameters
    valid = verify_token(
        token=token, client_id="token_test", tool_id="write_file", secret=Config.HMAC_SECRET
    )
    assert valid is True

    # Reject with wrong client_id
    invalid = verify_token(
        token=token, client_id="wrong_client", tool_id="write_file", secret=Config.HMAC_SECRET
    )
    assert invalid is False

    # Reject with wrong tool_id
    invalid = verify_token(
        token=token, client_id="token_test", tool_id="wrong_tool", secret=Config.HMAC_SECRET
    )
    assert invalid is False


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_capability_token_expiration(redis_client):
    """
    Verify capability tokens expire after TTL.

    Flow:
    1. Generate token with 1 second TTL
    2. Verify immediately (should succeed)
    3. Wait 2 seconds
    4. Verify again (should fail)
    """
    # Generate token with short TTL
    token = generate_token(
        client_id="expire_token_test",
        tool_id="write_file",
        ttl_seconds=1,
        secret=Config.HMAC_SECRET,
    )

    # Immediate verification succeeds
    valid = verify_token(
        token=token, client_id="expire_token_test", tool_id="write_file", secret=Config.HMAC_SECRET
    )
    assert valid is True

    # Wait for expiration
    time.sleep(2)

    # Verification should fail
    expired = verify_token(
        token=token, client_id="expire_token_test", tool_id="write_file", secret=Config.HMAC_SECRET
    )
    assert expired is False


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_lease_with_capability_token(redis_client):
    """
    Verify lease can be granted with capability token.

    Flow:
    1. Generate capability token
    2. Grant lease with token
    3. Lease includes token
    4. Token can be verified later
    """
    # Generate token
    token = generate_token(
        client_id="lease_token_test",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    # Grant lease with token
    lease = await lease_manager.grant(
        client_id="lease_token_test",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
        capability_token=token,
    )

    assert lease is not None
    assert lease.capability_token == token

    # Verify token is still valid
    valid = verify_token(
        token=lease.capability_token,
        client_id="lease_token_test",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid is True


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_mode_change_doesnt_affect_existing_leases(redis_client):
    """
    Verify mode changes don't affect existing leases.

    Security: Leases capture mode_at_issue, not current mode.

    Flow:
    1. Grant lease in PERMISSION mode
    2. Change mode to READ_ONLY
    3. Existing lease remains valid
    4. New leases follow new mode
    """
    # Set PERMISSION mode
    await governance_state.set_mode(ExecutionMode.PERMISSION)

    # Grant lease in PERMISSION mode
    lease = await lease_manager.grant(
        client_id="mode_change_test",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is not None
    assert lease.mode_at_issue == "PERMISSION"

    # Change to READ_ONLY mode
    await governance_state.set_mode(ExecutionMode.READ_ONLY)

    # Existing lease still valid
    validated = await lease_manager.validate("mode_change_test", "write_file")
    assert validated is not None
    assert validated.mode_at_issue == "PERMISSION"

    # New lease would capture new mode
    new_lease = await lease_manager.grant(
        client_id="mode_change_test_2",
        tool_id="read_file",
        ttl_seconds=300,
        calls_remaining=3,
        mode_at_issue="READ_ONLY",
    )
    assert new_lease.mode_at_issue == "READ_ONLY"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_empty_client_id_rejected(redis_client):
    """
    Verify empty client_id is rejected.

    Security: Prevents session isolation bypass.
    """
    # Empty string
    lease = await lease_manager.grant(
        client_id="",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is None

    # Whitespace only
    lease = await lease_manager.grant(
        client_id="   ",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=5,
        mode_at_issue="PERMISSION",
    )
    assert lease is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_complete_governance_lease_workflow(redis_client):
    """
    End-to-end test of governance + lease workflow.

    Flow:
    1. Policy check determines approval needed
    2. User approves (gets capability token)
    3. Lease granted with token
    4. Lease consumed on tool call
    5. Token verified at call time
    6. Lease expires after calls exhausted
    """
    # Step 1: Policy check
    decision = evaluate_policy(
        mode=ExecutionMode.PERMISSION, tool_risk="sensitive", tool_id="write_file"
    )
    assert decision.requires_approval

    # Step 2: User approval (simulate)
    token = generate_token(
        client_id="complete_flow_test",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    # Step 3: Grant lease
    lease = await lease_manager.grant(
        client_id="complete_flow_test",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=2,
        mode_at_issue="PERMISSION",
        capability_token=token,
    )
    assert lease is not None

    # Step 4: Consume lease (first call)
    consumed = await lease_manager.consume("complete_flow_test", "write_file")
    assert consumed.calls_remaining == 1

    # Step 5: Verify token
    valid = verify_token(
        token=consumed.capability_token,
        client_id="complete_flow_test",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid is True

    # Step 6: Exhaust lease
    consumed = await lease_manager.consume("complete_flow_test", "write_file")
    assert consumed.calls_remaining == 0

    # Lease deleted after exhaustion
    validated = await lease_manager.validate("complete_flow_test", "write_file")
    assert validated is None
