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
import hashlib
import hmac
import json
import time

import pytest

from src.meta_mcp.config import Config
from src.meta_mcp.governance.tokens import (
    canonicalize_json,
    decode_token,
    generate_token,
    verify_token,
)


def _sign_payload(payload: dict, secret: str) -> str:
    payload_bytes = canonicalize_json(payload)
    payload_b64 = base64.b64encode(payload_bytes).decode()
    signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


@pytest.mark.asyncio
async def test_token_forgery_rejected():
    """
    CRITICAL: Forged tokens with wrong HMAC secret must be rejected.
    """
    server_secret = Config.HMAC_SECRET
    server_token = generate_token(
        client_id="legitimate_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=server_secret,
    )

    payload_b64, _signature = server_token.split(".")
    payload = json.loads(base64.b64decode(payload_b64))
    payload["client_id"] = "attacker_session"

    forged_token = _sign_payload(payload, secret="ATTACKER_SECRET_12345")

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

    await asyncio.sleep(1.5)

    valid_expired = verify_token(
        token=token,
        client_id="test_session",
        tool_id="read_file",
        secret=Config.HMAC_SECRET,
    )
    assert valid_expired is False, "SECURITY BREACH: Expired token accepted!"


@pytest.mark.asyncio
async def test_token_replay_is_stateless():
    """
    Verify token verification is stateless by design.

    Replay protection is enforced via leases, not token verification.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    first_use = verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)
    assert first_use is True

    second_use = verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)
    assert second_use is True


@pytest.mark.asyncio
async def test_invalid_signature_rejected():
    """
    CRITICAL: Tokens with tampered payloads must be rejected.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload_b64, signature = token.split(".")
    payload = json.loads(base64.b64decode(payload_b64))
    payload["tool_id"] = "write_file"

    tampered_payload_b64 = base64.b64encode(canonicalize_json(payload)).decode()
    tampered_token = f"{tampered_payload_b64}.{signature}"

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
    """
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000)

    tokens = [
        generate_token(
            client_id="test_session",
            tool_id="write_file",
            ttl_seconds=300,
            secret=Config.HMAC_SECRET,
        )
        for _ in range(3)
    ]

    assert len(set(tokens)) == 1, "Token generation is non-deterministic!"


@pytest.mark.asyncio
async def test_token_client_id_binding():
    """
    CRITICAL: Token must be bound to specific client_id.
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
    """
    assert Config.HMAC_SECRET
    assert len(Config.HMAC_SECRET) >= 32, "HMAC_SECRET should be at least 32 bytes"


@pytest.mark.asyncio
async def test_token_contains_required_fields():
    """
    Verify token payload contains all required fields.
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
    """
    assert verify_token("payload_only", "session", "tool", Config.HMAC_SECRET) is False
    assert (
        verify_token("!!!invalid!!!.signature", "session", "tool", Config.HMAC_SECRET)
        is False
    )
    assert verify_token("part1.part2.part3", "session", "tool", Config.HMAC_SECRET) is False
    assert verify_token("", "session", "tool", Config.HMAC_SECRET) is False
    assert verify_token(None, "session", "tool", Config.HMAC_SECRET) is False


@pytest.mark.asyncio
async def test_token_generation_performance():
    """
    Verify token generation/verification are fast enough for real-time use.
    """
    iterations = 200
    start = time.perf_counter()
    for _ in range(iterations):
        token = generate_token(
            client_id="test_session",
            tool_id="write_file",
            ttl_seconds=300,
            secret=Config.HMAC_SECRET,
        )
    gen_time_ms = (time.perf_counter() - start) * 1000 / iterations

    assert gen_time_ms < 50, f"Token generation too slow: {gen_time_ms:.2f}ms"

    start = time.perf_counter()
    for _ in range(iterations):
        verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)
    verify_time_ms = (time.perf_counter() - start) * 1000 / iterations

    assert verify_time_ms < 20, f"Token verification too slow: {verify_time_ms:.2f}ms"


@pytest.mark.asyncio
async def test_token_missing_exp_rejected():
    """
    SECURITY: Tokens without exp should be rejected.
    """
    payload = {
        "client_id": "session",
        "tool_id": "read_file",
        "iat": int(time.time()),
    }
    token = _sign_payload(payload, Config.HMAC_SECRET)
    assert verify_token(token, "session", "read_file", Config.HMAC_SECRET) is False


@pytest.mark.asyncio
async def test_token_missing_client_id_rejected():
    """
    SECURITY: Tokens missing client_id should be rejected.
    """
    payload = {
        "tool_id": "read_file",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
    }
    token = _sign_payload(payload, Config.HMAC_SECRET)
    assert verify_token(token, "session", "read_file", Config.HMAC_SECRET) is False


@pytest.mark.asyncio
async def test_token_missing_tool_id_rejected():
    """
    SECURITY: Tokens missing tool_id should be rejected.
    """
    payload = {
        "client_id": "session",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
    }
    token = _sign_payload(payload, Config.HMAC_SECRET)
    assert verify_token(token, "session", "read_file", Config.HMAC_SECRET) is False


@pytest.mark.asyncio
async def test_token_non_canonical_payload_rejected():
    """
    SECURITY: Non-canonical payload encoding should be rejected.
    """
    payload = {
        "client_id": "session",
        "tool_id": "read_file",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
    }
    non_canonical = json.dumps(payload, separators=(", ", ": ")).encode("utf-8")
    payload_b64 = base64.b64encode(non_canonical).decode()
    signature = hmac.new(
        Config.HMAC_SECRET.encode(), non_canonical, hashlib.sha256
    ).hexdigest()
    token = f"{payload_b64}.{signature}"

    assert verify_token(token, "session", "read_file", Config.HMAC_SECRET) is False


@pytest.mark.asyncio
async def test_token_unicode_client_id_supported():
    """
    SECURITY: Unicode client IDs are supported.
    """
    token = generate_token(
        client_id="sessión-测试",
        tool_id="read_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )
    assert verify_token(token, "sessión-测试", "read_file", Config.HMAC_SECRET) is True


@pytest.mark.asyncio
async def test_token_special_characters_tool_id_supported():
    """
    SECURITY: Special characters in tool_id are supported.
    """
    tool_id = "tool:write_file@v2"
    token = generate_token(
        client_id="test_session",
        tool_id=tool_id,
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )
    assert verify_token(token, "test_session", tool_id, Config.HMAC_SECRET) is True


@pytest.mark.asyncio
async def test_token_secret_rotation_invalidates_old_tokens():
    """
    SECURITY: Tokens signed with old secret should fail with new secret.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=300,
        secret="old_secret_value_which_is_long_enough_12345",
    )

    assert verify_token(token, "test_session", "read_file", Config.HMAC_SECRET) is False


@pytest.mark.asyncio
async def test_token_exp_in_future_accepted():
    """
    SECURITY: Tokens with future expiration are accepted.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=60,
        secret=Config.HMAC_SECRET,
    )
    assert verify_token(token, "test_session", "read_file", Config.HMAC_SECRET) is True


@pytest.mark.asyncio
async def test_token_context_key_required_when_provided():
    """
    SECURITY: Context key must match when verification supplies one.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="read_file",
        ttl_seconds=60,
        secret=Config.HMAC_SECRET,
    )

    assert (
        verify_token(
            token,
            "test_session",
            "read_file",
            Config.HMAC_SECRET,
            context_key="path=/workspace/file.txt",
        )
        is False
    )


@pytest.mark.asyncio
async def test_token_signature_matches_hmac_sha256():
    """
    SECURITY: Token signatures use HMAC-SHA256.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload_b64, signature = token.split(".")
    payload_bytes = base64.b64decode(payload_b64)

    expected_signature = hmac.new(
        Config.HMAC_SECRET.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    assert signature == expected_signature


@pytest.mark.asyncio
async def test_token_payload_roundtrip_matches_decode():
    """
    SECURITY: decode_token round-trips payload fields.
    """
    token = generate_token(
        client_id="decode_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload = decode_token(token)
    assert payload is not None
    assert payload["client_id"] == "decode_session"
    assert payload["tool_id"] == "write_file"


@pytest.mark.asyncio
async def test_token_payload_is_canonical():
    """
    SECURITY: Generated payload bytes should be canonical JSON.
    """
    token = generate_token(
        client_id="canonical_session",
        tool_id="read_file",
        ttl_seconds=60,
        secret=Config.HMAC_SECRET,
    )

    payload_b64, _signature = token.split(".")
    payload_bytes = base64.b64decode(payload_b64)
    payload = json.loads(payload_bytes)

    assert payload_bytes == canonicalize_json(payload)
