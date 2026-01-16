"""Capability token generation and verification (Phase 4)."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from loguru import logger


def generate_token(
    client_id: str,
    tool_id: str,
    ttl_seconds: int,
    secret: str,
    context_key: str | None = None,
) -> str:
    """
    Generate HMAC-SHA256 signed capability token.

    Token Format: base64(payload).signature
    - Payload: JSON with {client_id, tool_id, exp, iat, context_key}
    - Signature: HMAC-SHA256(payload, secret)

    Args:
        client_id: Session identifier
        tool_id: Tool identifier
        ttl_seconds: Time-to-live in seconds
        secret: HMAC secret key
        context_key: Optional context scoping (e.g., "path=/workspace/data.txt")

    Returns:
        Signed capability token string

    Security:
    - Deterministic canonicalization (sorted JSON keys)
    - HMAC-SHA256 signature prevents forgery
    - Expiration timestamp prevents replay attacks
    - Client and tool binding prevents cross-session/tool reuse

    Design Plan Section 5.1
    """
    # Compute timestamps
    iat = int(time.time())
    exp = iat + ttl_seconds

    # Build payload
    payload = {
        "client_id": client_id,
        "tool_id": tool_id,
        "exp": exp,
        "iat": iat,
    }

    if context_key is not None:
        payload["context_key"] = context_key

    # Canonical JSON (sorted keys for determinism)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_b64 = base64.b64encode(payload_json.encode()).decode()

    # Compute HMAC-SHA256 signature
    signature = hmac.new(
        secret.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).hexdigest()

    # Return token
    token = f"{payload_b64}.{signature}"
    return token


def verify_token(
    token: str,
    client_id: str,
    tool_id: str,
    secret: str,
    context_key: str | None = None,
) -> bool:
    """
    Verify capability token signature and claims.

    Checks:
    1. Token format is valid
    2. Signature matches payload
    3. Token is not expired
    4. client_id matches
    5. tool_id matches
    6. context_key matches (if provided)

    Args:
        token: Capability token to verify
        client_id: Expected session identifier
        tool_id: Expected tool identifier
        secret: HMAC secret key
        context_key: Expected context key (if token has one)

    Returns:
        True if token is valid, False otherwise

    Security:
    - Constant-time comparison for HMAC signatures
    - Fails closed on any validation error
    - Rejects expired tokens
    - Enforces client and tool binding

    Design Plan Section 5.2
    """
    if not token:
        logger.warning("Token verification failed: empty token")
        return False

    try:
        # Parse token
        parts = token.split(".")
        if len(parts) != 2:
            logger.warning("Token verification failed: invalid format")
            return False

        payload_b64, signature = parts

        # Verify signature
        expected_signature = hmac.new(
            secret.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("Token verification failed: invalid signature")
            return False

        # Decode payload
        payload_json = base64.b64decode(payload_b64).decode()
        payload = json.loads(payload_json)

        # Check expiration
        exp = payload.get("exp")
        if exp is None or time.time() > exp:
            logger.warning("Token verification failed: expired")
            return False

        # Check client_id
        if payload.get("client_id") != client_id:
            logger.warning(
                f"Token verification failed: client_id mismatch "
                f"(expected={client_id}, got={payload.get('client_id')})"
            )
            return False

        # Check tool_id
        if payload.get("tool_id") != tool_id:
            logger.warning(
                f"Token verification failed: tool_id mismatch "
                f"(expected={tool_id}, got={payload.get('tool_id')})"
            )
            return False

        # Check context_key if provided
        if context_key is not None:
            if payload.get("context_key") != context_key:
                logger.warning(
                    f"Token verification failed: context_key mismatch "
                    f"(expected={context_key}, got={payload.get('context_key')})"
                )
                return False

        # All checks passed
        return True

    except (ValueError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Token verification failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in token verification: {e}")
        return False


def decode_token(token: str) -> dict[str, Any] | None:
    """
    Decode token payload WITHOUT verification.

    WARNING: This does NOT verify the signature. Only use for debugging
    or logging. Never trust the decoded data without verify_token().

    Args:
        token: Capability token to decode

    Returns:
        Decoded payload dict, or None if parsing fails

    Design Plan Section 5.3
    """
    if not token:
        return None

    try:
        # Parse token
        parts = token.split(".")
        if len(parts) != 2:
            return None

        payload_b64, _ = parts

        # Decode payload
        payload_json = base64.b64decode(payload_b64).decode()
        payload = json.loads(payload_json)

        return payload

    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Token decode failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in token decode: {e}")
        return None
