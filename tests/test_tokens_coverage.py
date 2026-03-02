"""Tests for governance tokens module coverage gaps.

Covers non-canonical base64, decode_token edge cases, and exception handling.
"""

import base64
import json
import time
from unittest.mock import patch

import pytest

from src.meta_mcp.governance.tokens import (
    decode_token,
    generate_token,
    verify_token,
)


class TestVerifyTokenEdgeCases:
    def test_non_canonical_base64(self):
        """Test that non-canonical base64 padding is rejected."""
        # Generate a valid token
        token = generate_token("client-1", "tool-1", 300, "secret")
        payload_b64, sig = token.split(".")
        # Add padding to make it non-canonical
        mangled_b64 = payload_b64 + "=="
        mangled_token = f"{mangled_b64}.{sig}"
        result = verify_token(mangled_token, "client-1", "tool-1", "secret")
        assert result is False

    def test_verify_invalid_base64(self):
        """Test token with invalid base64 chars."""
        result = verify_token("!!!invalid!!!.badsig", "c", "t", "s")
        assert result is False

    def test_verify_unexpected_exception(self):
        """Test unexpected exception in verify_token."""
        with patch(
            "src.meta_mcp.governance.tokens.base64.b64decode",
            side_effect=TypeError("unexpected"),
        ):
            result = verify_token("dGVzdA==.sig", "c", "t", "s")
            assert result is False


class TestDecodeTokenEdgeCases:
    def test_decode_empty_token(self):
        assert decode_token("") is None

    def test_decode_no_dot(self):
        assert decode_token("nodot") is None

    def test_decode_too_many_dots(self):
        assert decode_token("a.b.c") is None

    def test_decode_invalid_base64(self):
        assert decode_token("!!!.sig") is None

    def test_decode_invalid_json(self):
        # Valid base64 but not valid JSON
        b64 = base64.b64encode(b"not-json").decode()
        assert decode_token(f"{b64}.sig") is None

    def test_decode_valid_token(self):
        token = generate_token("client-1", "tool-1", 300, "secret")
        payload = decode_token(token)
        assert payload is not None
        assert payload["client_id"] == "client-1"
        assert payload["tool_id"] == "tool-1"

    def test_decode_unexpected_exception(self):
        """Cover the generic Exception handler in decode_token."""
        with patch(
            "src.meta_mcp.governance.tokens.base64.b64decode",
            side_effect=TypeError("unexpected"),
        ):
            result = decode_token("dGVzdA==.sig")
            assert result is None
