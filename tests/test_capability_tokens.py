"""
Unit Tests for Capability Token Generation and Verification (Phase 4)

Tests token operations:
- generate_token(): Create HMAC-signed tokens
- verify_token(): Verify token signature and expiration
- decode_token(): Decode token payload without verification
- Token format and structure
"""


import base64
import json

import pytest

from src.meta_mcp.config import Config
from src.meta_mcp.governance.tokens import generate_token, verify_token


@pytest.mark.asyncio
async def test_generate_token_creates_valid_token():
    """
    Verify generate_token() creates a properly formatted token.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token
    # from src.meta_mcp.config import Config

    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Token format: base64(payload).signature
    # assert isinstance(token, str)
    # assert "." in token
    # parts = token.split(".")
    # assert len(parts) == 2



@pytest.mark.asyncio
async def test_verify_token_validates_signature():
    """
    Verify verify_token() checks HMAC signature.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token, verify_token
    # from src.meta_mcp.config import Config

    # Generate valid token
    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Verify with correct secret
    # valid = verify_token(
    #     token=token,
    #     client_id="test_session",
    #     tool_id="write_file",
    #     secret=Config.HMAC_SECRET
    # )
    # assert valid is True

    # Verify with wrong secret
    # invalid = verify_token(
    #     token=token,
    #     client_id="test_session",
    #     tool_id="write_file",
    #     secret="WRONG_SECRET"
    # )
    # assert invalid is False



@pytest.mark.asyncio
async def test_verify_token_checks_expiration():
    """
    Verify verify_token() rejects expired tokens.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token, verify_token
    # from src.meta_mcp.config import Config
    # import asyncio

    # Generate token with 1 second TTL
    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     ttl_seconds=1,
    #     secret=Config.HMAC_SECRET
    # )

    # Valid immediately
    # assert verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)

    # Wait for expiration
    # await asyncio.sleep(2)

    # Now invalid
    # assert not verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)



@pytest.mark.asyncio
async def test_verify_token_checks_client_id():
    """
    Verify verify_token() validates client_id binding.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token, verify_token
    # from src.meta_mcp.config import Config

    # Generate token for session A
    # token = generate_token(
    #     client_id="session_a",
    #     tool_id="write_file",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Verify with correct client_id
    # assert verify_token(token, "session_a", "write_file", Config.HMAC_SECRET)

    # Verify with wrong client_id
    # assert not verify_token(token, "session_b", "write_file", Config.HMAC_SECRET)



@pytest.mark.asyncio
async def test_verify_token_checks_tool_id():
    """
    Verify verify_token() validates tool_id binding.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token, verify_token
    # from src.meta_mcp.config import Config

    # Generate token for write_file
    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Verify with correct tool_id
    # assert verify_token(token, "test_session", "write_file", Config.HMAC_SECRET)

    # Verify with wrong tool_id
    # assert not verify_token(token, "test_session", "delete_file", Config.HMAC_SECRET)



@pytest.mark.asyncio
async def test_decode_token_without_verification():
    """
    Verify decode_token() extracts payload without signature check.

    Useful for debugging and logging (but never trust decoded data).
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token, decode_token
    # from src.meta_mcp.config import Config

    # Generate token
    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Decode payload
    # payload = decode_token(token)

    # Verify payload structure
    # assert payload["client_id"] == "test_session"
    # assert payload["tool_id"] == "write_file"
    # assert "exp" in payload
    # assert "iat" in payload



@pytest.mark.asyncio
async def test_token_with_context_key():
    """
    Verify tokens can include optional context_key.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token, verify_token
    # from src.meta_mcp.config import Config

    # Generate token with context
    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     context_key="path=/workspace/data.txt",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Verify with matching context
    # assert verify_token(
    #     token,
    #     "test_session",
    #     "write_file",
    #     Config.HMAC_SECRET,
    #     context_key="path=/workspace/data.txt"
    # )

    # Verify fails with different context
    # assert not verify_token(
    #     token,
    #     "test_session",
    #     "write_file",
    #     Config.HMAC_SECRET,
    #     context_key="path=/workspace/other.txt"
    # )


@pytest.mark.asyncio
async def test_reordered_payload_rejected():
    """
    Verify that reordered payload keys fail verification.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload_b64, signature = token.split(".")
    payload = json.loads(base64.b64decode(payload_b64))

    tampered_payload = {
        "tool_id": payload["tool_id"],
        "client_id": payload["client_id"],
        "iat": payload["iat"],
        "exp": payload["exp"],
    }

    if "context_key" in payload:
        tampered_payload["context_key"] = payload["context_key"]

    tampered_json = json.dumps(tampered_payload, separators=(",", ":"))
    tampered_b64 = base64.b64encode(tampered_json.encode()).decode()
    tampered_token = f"{tampered_b64}.{signature}"

    assert (
        verify_token(
            token=tampered_token,
            client_id="test_session",
            tool_id="write_file",
            secret=Config.HMAC_SECRET,
        )
        is False
    )


@pytest.mark.asyncio
async def test_whitespace_payload_rejected():
    """
    Verify that non-canonical whitespace changes fail verification.
    """
    token = generate_token(
        client_id="test_session",
        tool_id="write_file",
        ttl_seconds=300,
        secret=Config.HMAC_SECRET,
    )

    payload_b64, signature = token.split(".")
    payload = json.loads(base64.b64decode(payload_b64))

    tampered_json = json.dumps(payload, separators=(", ", ": "))
    tampered_b64 = base64.b64encode(tampered_json.encode()).decode()
    tampered_token = f"{tampered_b64}.{signature}"

    assert (
        verify_token(
            token=tampered_token,
            client_id="test_session",
            tool_id="write_file",
            secret=Config.HMAC_SECRET,
        )
        is False
    )



@pytest.mark.asyncio
async def test_hmac_sha256_algorithm():
    """
    Verify tokens use HMAC-SHA256 for signing.
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token
    # from src.meta_mcp.config import Config
    # import hmac
    # import hashlib
    # import base64
    # import json

    # Generate token
    # token = generate_token(
    #     client_id="test_session",
    #     tool_id="write_file",
    #     ttl_seconds=300,
    #     secret=Config.HMAC_SECRET
    # )

    # Split token
    # payload_b64, signature = token.split(".")

    # Decode payload
    # payload = json.loads(base64.b64decode(payload_b64))

    # Recompute signature
    # expected_signature = hmac.new(
    #     Config.HMAC_SECRET.encode(),
    #     payload_b64.encode(),
    #     hashlib.sha256
    # ).hexdigest()

    # Verify signatures match
    # assert signature == expected_signature



@pytest.mark.asyncio
async def test_token_canonicalization():
    """
    Verify token generation is deterministic (same input = same output).
    """
    # TODO: Implement after Phase 4
    # from src.meta_mcp.governance.tokens import generate_token
    # from src.meta_mcp.config import Config

    # Generate same token multiple times
    # tokens = []
    # for _ in range(10):
    #     token = generate_token(
    #         client_id="test_session",
    #         tool_id="write_file",
    #         ttl_seconds=300,
    #         secret=Config.HMAC_SECRET
    #     )
    #     # Extract payload only (timestamp will differ)
    #     payload_b64 = token.split(".")[0]
    #     tokens.append(payload_b64)

    # Note: Timestamps will differ, so tokens won't be identical
    # But payload structure should be consistent
    # This test documents expected non-determinism due to timestamps
