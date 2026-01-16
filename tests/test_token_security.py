"""
CRITICAL Security Tests for Phase 4 (Governance Engine - Capability Tokens)

These tests MUST pass 100% before Phase 4 is considered complete.

Phase 4 implements capability tokens with HMAC-SHA256 signing for approval
verification. This is the primary defense against governance bypass attacks.

Security Requirements:
1. Token Forgery Prevention: Tokens with wrong HMAC secret MUST be rejected
2. Token Expiration: Expired tokens MUST be rejected
3. Token Replay Prevention: Same token cannot be used multiple times
4. Payload Tampering: Modified payloads MUST fail signature verification
5. Deterministic Canonicalization: Token generation must be deterministic

This is the #1 security critical component of Phase 4.
"""

import asyncio
import base64
import json
import time

import pytest

from src.meta_mcp.config import Config
from src.meta_mcp.governance import tokens
from src.meta_mcp.governance.tokens import decode_token, generate_token, verify_token
from src.meta_mcp.leases import lease_manager


@pytest.mark.asyncio
async def test_token_forgery_rejected():
    """
    CRITICAL: Forged tokens with wrong HMAC secret must be rejected.

    Security Risk: Token forgery = complete governance bypass.
    This is the #1 security test for Phase 4.

    Attack Scenario:
    1. Attacker sees approval_required response
    2. Attacker tries to forge token with their own secret
    3. Server must reject because HMAC verification fails
    4. Tool call must be denied

    If this test fails, STOP Phase 4 implementation immediately.
    """
    server_secret = Config.HMAC_SECRET
    server_token = generate_token(
        client_id="legitimate_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=server_secret,
    )

    attacker_secret = "ATTACKER_SECRET_12345"
    forged_token = generate_token(
        client_id="attacker_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=attacker_secret,
    )

    forged_valid = verify_token(
        token=forged_token,
        client_id="attacker_session",
        tool_id="write_file",
        secret=server_secret,
    )
    assert forged_valid is False, "SECURITY BREACH: Forged token accepted!"

    legit_valid = verify_token(
        token=server_token,
        client_id="legitimate_session",
        tool_id="write_file",
        secret=server_secret,
    )
    assert legit_valid is True, "Legitimate token should be accepted"


@pytest.mark.asyncio
async def test_expired_token_rejected():
    """
    CRITICAL: Expired tokens must be rejected.

    Security Risk: Token replay attacks allow reusing old approvals.

    Attack Scenario:
    1. User approves write_file operation (gets token with 5 min TTL)
    2. 10 minutes later, attacker tries to reuse the token
    3. Server must reject because token is expired
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=1,
        secret=Config.HMAC_SECRET,
    )

    valid_now = verify_token(
        token=token,
        client_id="test_session",
        tool_id="read_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_now is True, "Token should be valid immediately"

    await asyncio.sleep(2)

    valid_expired = verify_token(
        token=token,
        client_id="test_session",
        tool_id="read_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_expired is False, "SECURITY BREACH: Expired token accepted!"


@pytest.mark.asyncio
@pytest.mark.requires_redis
async def test_token_replay_prevention(redis_client):
    """
    CRITICAL: Same token cannot be used multiple times.

    Security Risk: Token replay allows reusing single approval
    for multiple tool calls.

    Attack Scenario:
    1. User approves write_file for /data/config.json
    2. Attacker captures the token
    3. Attacker tries to use same token for write_file /data/secrets.json
    4. Server must reject because token was already consumed

    Note: Current design may track token usage in Redis to prevent replay.
    Verify implementation matches this requirement.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    lease = await lease_manager.grant(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        calls_remaining=1,
        mode_at_issue="PERMISSION",
        capability_token=token,
    )
    assert lease is not None

    first_use = await lease_manager.consume("test_session", "write_file")
    assert first_use is not None
    assert first_use.calls_remaining == 0

    second_use = await lease_manager.consume("test_session", "write_file")
    assert second_use is None, "SECURITY BREACH: Token replay succeeded!"


@pytest.mark.asyncio
async def test_invalid_signature_rejected():
    """
    CRITICAL: Tokens with tampered payloads must be rejected.

    Security Risk: Payload tampering allows privilege escalation.

    Attack Scenario:
    1. User gets token for read_file
    2. Attacker modifies payload to change tool_id to write_file
    3. Signature no longer matches payload
    4. Server must reject because HMAC verification fails
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload_b64, original_signature = token.split(".")

    payload = json.loads(base64.b64decode(payload_b64))
    payload["tool_id"] = "write_file"
    tampered_payload_b64 = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()

    tampered_token = f"{tampered_payload_b64}.{original_signature}"

    valid = verify_token(
        token=tampered_token,
        client_id="test_session",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid is False, "SECURITY BREACH: Tampered token accepted!"


@pytest.mark.asyncio
async def test_token_canonicalization_deterministic(monkeypatch):
    """
    Verify token canonicalization produces same result every time.

    Non-deterministic canonicalization would cause false rejections.
    For example, if dict serialization order is random, same approval
    could generate different tokens each time.

    This test ensures token generation is deterministic.
    """
    fixed_time = 1_700_000_000
    monkeypatch.setattr(tokens.time, "time", lambda: fixed_time)

    generated = [
        generate_token(
            client_id="test_session",
            tool_id="write_file",
            ttl_seconds=300,
            secret=Config.HMAC_SECRET,
        )
        for _ in range(5)
    ]

    assert len(set(generated)) == 1, "Token generation is non-deterministic!"


@pytest.mark.asyncio
async def test_token_client_id_binding():
    """
    CRITICAL: Token must be bound to specific client_id.

    Security Risk: Without client binding, token from one session
    could be used in another session.

    Attack Scenario:
    1. User in session A approves write_file
    2. Attacker in session B captures token
    3. Attacker tries to use token in session B
    4. Server must reject because client_id doesn't match
    """
    token = generate_token(
        client_id="session_a",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    valid_a = verify_token(
        token=token,
        client_id="session_a",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_a is True

    valid_b = verify_token(
        token=token,
        client_id="session_b",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_b is False, "SECURITY BREACH: Token used across sessions!"


@pytest.mark.asyncio
async def test_token_tool_id_binding():
    """
    CRITICAL: Token must be bound to specific tool_id.

    Security Risk: Without tool binding, token approved for one tool
    could be used for another tool.

    Attack Scenario:
    1. User approves read_file
    2. Attacker tries to use same token for write_file
    3. Server must reject because tool_id doesn't match
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    valid_read = verify_token(
        token=token,
        client_id="test_session",
        tool_id="read_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_read is True

    valid_write = verify_token(
        token=token,
        client_id="test_session",
        tool_id="write_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_write is False, "SECURITY BREACH: Token used for wrong tool!"


@pytest.mark.asyncio
async def test_hmac_secret_not_empty():
    """
    CRITICAL: HMAC_SECRET must be configured.

    Security Risk: Empty secret makes all tokens trivially forgeable.

    This test should fail during development if HMAC_SECRET not set,
    forcing developer to configure it before Phase 4 can be deployed.
    """
    assert Config.HMAC_SECRET != "", "HMAC_SECRET must be configured"
    assert Config.HMAC_SECRET is not None, "HMAC_SECRET must be configured"
    assert len(Config.HMAC_SECRET) >= 32, "HMAC_SECRET should be at least 32 bytes"


@pytest.mark.asyncio
async def test_token_contains_required_fields():
    """
    Verify token payload contains all required fields.

    Required fields:
    - client_id: Session identifier
    - tool_id: Tool being approved
    - exp: Expiration timestamp
    - iat: Issued at timestamp

    Optional fields:
    - context_key: Additional context (e.g., file path)
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload = decode_token(token)
    assert payload is not None

    assert "client_id" in payload
    assert "tool_id" in payload
    assert "exp" in payload
    assert "iat" in payload

    assert payload["client_id"] == "test_session"
    assert payload["tool_id"] == "write_file"
    assert payload["exp"] > payload["iat"]


@pytest.mark.asyncio
async def test_token_with_context_key():
    """
    Verify tokens can include context_key for additional scoping.

    Context key example: "path=/workspace/data.txt"
    This allows token to be valid only for specific file path.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        context_key="path=/workspace/data.txt",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    valid_match = verify_token(
        token=token,
        client_id="test_session",
        tool_id="write_file",
        context_key="path=/workspace/data.txt",
        secret=Config.HMAC_SECRET,
    )
    assert valid_match is True

    valid_mismatch = verify_token(
        token=token,
        client_id="test_session",
        tool_id="write_file",
        context_key="path=/workspace/other.txt",
        secret=Config.HMAC_SECRET,
    )
    assert valid_mismatch is False, "Token should be invalid for different context"


@pytest.mark.asyncio
async def test_malformed_token_rejected():
    """
    Verify malformed tokens are rejected gracefully.

    Test cases:
    - Token with missing signature
    - Token with invalid base64
    - Token with invalid JSON payload
    - Token with wrong number of parts
    """
    assert verify_token("payload_only", "session", "tool", Config.HMAC_SECRET) is False
    assert (
        verify_token("!!!invalid!!!.signature", "session", "tool", Config.HMAC_SECRET)
        is False
    )
    assert verify_token("part1.part2.part3", "session", "tool", Config.HMAC_SECRET) is False
    assert verify_token("", "session", "tool", Config.HMAC_SECRET) is False
    assert verify_token(None, "session", "tool", Config.HMAC_SECRET) is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_token_generation_performance():
    """
    Verify token generation is fast enough for real-time use.

    Target: < 10ms per token generation
    Target: < 5ms per token verification

    Token operations are on the hot path for every approval,
    so performance matters.
    """
    start = time.perf_counter()
    for _ in range(100):
        token = generate_token(
            client_id="test_session",
            tool_id="write_file",
            ttl_seconds=300,
            secret=Config.HMAC_SECRET,
        )
    gen_time_ms = (time.perf_counter() - start) * 1000 / 100

    assert gen_time_ms < 10, f"Token generation too slow: {gen_time_ms:.2f}ms"

    start = time.perf_counter()
    for _ in range(100):
        verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)
    verify_time_ms = (time.perf_counter() - start) * 1000 / 100

    assert verify_time_ms < 5, f"Token verification too slow: {verify_time_ms:.2f}ms"
