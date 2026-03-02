"""Targeted coverage tests for governance/approval.py and governance/artifacts.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ============================================================================
# APPROVAL PARSING TESTS (approval.py static methods)
# ============================================================================


class TestParseStructuredResponse:
    """Tests for FastMCPElicitProvider._parse_structured_response."""

    def test_none_returns_empty(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_structured_response(None) == {}

    def test_dict_normalizes_keys(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_structured_response({"Decision": "approved", "SCOPES": []})
        assert result == {"decision": "approved", "scopes": []}

    def test_empty_string_returns_empty(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_structured_response("") == {}
        assert FastMCPElicitProvider._parse_structured_response("   ") == {}

    def test_valid_json_string(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        payload = '{"Decision": "approved", "selected_scopes": ["scope1"]}'
        result = FastMCPElicitProvider._parse_structured_response(payload)
        assert result["decision"] == "approved"

    def test_invalid_json_falls_back_to_kv(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_structured_response("decision=approved\nlease_seconds=300")
        assert result["decision"] == "approved"
        assert result["lease_seconds"] == "300"

    def test_non_string_non_dict_returns_empty(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_structured_response(42) == {}
        assert FastMCPElicitProvider._parse_structured_response([1, 2]) == {}


class TestParseKeyValueResponse:
    """Tests for FastMCPElicitProvider._parse_key_value_response."""

    def test_equals_separator(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_key_value_response("key=value")
        assert result["key"] == "value"

    def test_colon_separator(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_key_value_response("key: value")
        assert result["key"] == "value"

    def test_semicolon_chunks(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_key_value_response("a=1;b=2")
        assert result["a"] == "1"
        assert result["b"] == "2"

    def test_empty_lines_skipped(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_key_value_response("  \nkey=val\n  ")
        assert result["key"] == "val"

    def test_no_separator_skipped(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_key_value_response("no_separator_here")
        assert result == {}


class TestParseDecision:
    """Tests for FastMCPElicitProvider._parse_decision."""

    def test_none_returns_none(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_decision(None) is None

    def test_approved_variants(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        for val in ("approved", "approve", "yes", "y", "APPROVED", "YES"):
            result = FastMCPElicitProvider._parse_decision(val)
            assert result == ApprovalDecision.APPROVED, f"Failed for {val!r}"

    def test_denied_variants(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        for val in ("denied", "deny", "no", "n", "DENIED", "NO"):
            result = FastMCPElicitProvider._parse_decision(val)
            assert result == ApprovalDecision.DENIED, f"Failed for {val!r}"

    def test_timeout(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_decision("timeout") == ApprovalDecision.TIMEOUT

    def test_error(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_decision("error") == ApprovalDecision.ERROR

    def test_unknown_returns_none(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_decision("maybe") is None
        assert FastMCPElicitProvider._parse_decision("perhaps") is None


class TestParseScopes:
    """Tests for FastMCPElicitProvider._parse_scopes."""

    def test_none_returns_empty(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_scopes(None) == []

    def test_list_input(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_scopes(["scope1", "scope2", "  "])
        assert result == ["scope1", "scope2"]

    def test_empty_string_returns_empty(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_scopes("") == []
        assert FastMCPElicitProvider._parse_scopes("  ") == []

    def test_json_list_string(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_scopes('["scope1", "scope2"]')
        assert result == ["scope1", "scope2"]

    def test_invalid_json_list_string_falls_back_to_csv(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_scopes("[not valid json")
        assert "not valid json" in result[0] or len(result) > 0

    def test_csv_string(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_scopes("scope1, scope2, scope3")
        assert result == ["scope1", "scope2", "scope3"]

    def test_non_string_non_list_single_value(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        result = FastMCPElicitProvider._parse_scopes(42)
        assert result == ["42"]

    def test_zero_treated_as_empty_string_representation(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        # 0 converts to "0" which is non-empty, so returns ["0"]
        result = FastMCPElicitProvider._parse_scopes(0)
        assert result == ["0"]


class TestParseLeaseSeconds:
    """Tests for FastMCPElicitProvider._parse_lease_seconds."""

    def test_none_returns_zero(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_lease_seconds(None) == 0

    def test_int_value(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_lease_seconds(300) == 300

    def test_float_value(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_lease_seconds(300.7) == 300

    def test_string_value(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_lease_seconds("120") == 120

    def test_invalid_string_returns_zero(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_lease_seconds("not-a-number") == 0

    def test_negative_clamped_to_zero(self):
        from src.meta_mcp.governance.approval import FastMCPElicitProvider
        assert FastMCPElicitProvider._parse_lease_seconds(-100) == 0


class TestParseApprovalPayload:
    """Tests for FastMCPElicitProvider._parse_approval_payload."""

    def _make_request(self):
        from src.meta_mcp.governance.approval import ApprovalRequest
        return ApprovalRequest(
            request_id="test-req",
            tool_name="write_file",
            message="Test message",
            required_scopes=["scope1"],
        )

    def test_payload_with_data_attribute(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        payload = MagicMock()
        payload.data = '{"decision": "approved", "selected_scopes": ["scope1"], "lease_seconds": 60}'
        request = self._make_request()
        result = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert result.decision == ApprovalDecision.APPROVED
        assert result.selected_scopes == ["scope1"]
        assert result.lease_seconds == 60

    def test_empty_payload_returns_error(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        request = self._make_request()
        result = FastMCPElicitProvider._parse_approval_payload(request, "")
        assert result.decision == ApprovalDecision.ERROR

    def test_payload_with_no_decision_inferred_from_scopes(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        payload = '{"selected_scopes": ["scope1"], "lease_seconds": 0}'
        request = self._make_request()
        result = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert result.decision == ApprovalDecision.APPROVED

    def test_payload_with_no_decision_and_no_scopes_infers_denied(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider
        payload = '{"selected_scopes": [], "lease_seconds": 0}'
        request = self._make_request()
        result = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert result.decision == ApprovalDecision.DENIED


class TestApprovalResponseIsApproved:
    """Tests for ApprovalResponse.is_approved()."""

    def test_approved_with_scopes(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, ApprovalResponse
        resp = ApprovalResponse(
            request_id="x",
            decision=ApprovalDecision.APPROVED,
            selected_scopes=["scope1"],
        )
        assert resp.is_approved() is True

    def test_approved_without_scopes(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, ApprovalResponse
        resp = ApprovalResponse(
            request_id="x",
            decision=ApprovalDecision.APPROVED,
            selected_scopes=[],
        )
        assert resp.is_approved() is False

    def test_denied(self):
        from src.meta_mcp.governance.approval import ApprovalDecision, ApprovalResponse
        resp = ApprovalResponse(
            request_id="x",
            decision=ApprovalDecision.DENIED,
            selected_scopes=["scope1"],
        )
        assert resp.is_approved() is False


# ============================================================================
# APPROVAL PROVIDER FACTORY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_fastmcp_elicit_provider_not_available_without_context():
    """Test FastMCPElicitProvider.is_available() returns False when no context."""
    from src.meta_mcp.governance.approval import FastMCPElicitProvider
    provider = FastMCPElicitProvider()
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_fastmcp_elicit_provider_available_with_context():
    """Test FastMCPElicitProvider.is_available() returns True when context has elicit."""
    from src.meta_mcp.governance.approval import FastMCPElicitProvider
    ctx = MagicMock()
    ctx.elicit = MagicMock()
    provider = FastMCPElicitProvider(ctx)
    assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_fastmcp_elicit_provider_name():
    from src.meta_mcp.governance.approval import FastMCPElicitProvider
    provider = FastMCPElicitProvider()
    assert provider.get_name() == "FastMCP Elicit"


@pytest.mark.asyncio
async def test_dbus_provider_name():
    from src.meta_mcp.governance.approval import DBusGUIProvider
    provider = DBusGUIProvider()
    assert provider.get_name() == "DBus GUI"


@pytest.mark.asyncio
async def test_systemd_provider_name():
    from src.meta_mcp.governance.approval import SystemdFallbackProvider
    provider = SystemdFallbackProvider()
    assert provider.get_name() == "systemd Fallback"


@pytest.mark.asyncio
async def test_fastmcp_elicit_request_not_available():
    """Test FastMCPElicitProvider.request_approval() when not available."""
    from src.meta_mcp.governance.approval import (
        ApprovalDecision,
        ApprovalRequest,
        FastMCPElicitProvider,
    )
    provider = FastMCPElicitProvider()  # No context
    request = ApprovalRequest(
        request_id="req-1",
        tool_name="write_file",
        message="Test",
        required_scopes=["scope1"],
    )
    response = await provider.request_approval(request)
    assert response.decision == ApprovalDecision.ERROR


@pytest.mark.asyncio
async def test_dbus_provider_is_available_false_without_dasbus():
    """Test DBusGUIProvider.is_available() returns False when dasbus not installed."""
    from src.meta_mcp.governance.approval import DBusGUIProvider
    provider = DBusGUIProvider()
    # dasbus is not installed in test env, so should return False
    result = await provider.is_available()
    assert result is False


@pytest.mark.asyncio
async def test_systemd_provider_is_available():
    """Test SystemdFallbackProvider.is_available() runs without error."""
    from src.meta_mcp.governance.approval import SystemdFallbackProvider
    provider = SystemdFallbackProvider()
    result = await provider.is_available()
    assert isinstance(result, bool)


# ============================================================================
# ARTIFACT GENERATOR TESTS (artifacts.py)
# ============================================================================


class TestApprovalArtifactGenerator:
    """Tests for ApprovalArtifactGenerator."""

    def test_init_creates_directory(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
        root = str(tmp_path / "test_artifacts")
        gen = ApprovalArtifactGenerator(artifacts_root=root)
        assert gen.artifacts_root.exists()

    def test_init_rejects_etc(self):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator, ArtifactGenerationError
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator(artifacts_root="/etc/artifacts")

    def test_init_rejects_usr(self):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator, ArtifactGenerationError
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator(artifacts_root="/usr/local/artifacts")

    def test_init_rejects_exact_root(self):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator, ArtifactGenerationError
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator(artifacts_root="/")

    def test_validate_path_traversal_blocked(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator, ArtifactGenerationError
        gen = ApprovalArtifactGenerator(artifacts_root=str(tmp_path / "arts"))
        with pytest.raises(ArtifactGenerationError):
            gen._validate_path("../../etc/passwd")

    def test_validate_path_valid(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
        gen = ApprovalArtifactGenerator(artifacts_root=str(tmp_path / "arts"))
        path = gen._validate_path("test.html")
        assert path.parent == gen.artifacts_root

    def test_generate_html_artifact(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
        gen = ApprovalArtifactGenerator(artifacts_root=str(tmp_path / "arts"))
        html_path = gen.generate_html_artifact(
            request_id="req-123",
            tool_name="write_file",
            message="Test approval",
            required_scopes=["scope1", "scope2"],
            arguments={"path": "test.txt", "content": "data"},
            context_metadata={"session_id": "sess-1", "context_key": "test.txt"},
        )
        assert Path(html_path).exists()
        content = Path(html_path).read_text()
        assert "write_file" in content
        assert "req-123" in content

    def test_generate_json_artifact(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
        gen = ApprovalArtifactGenerator(artifacts_root=str(tmp_path / "arts"))
        json_path = gen.generate_json_artifact(
            request_id="req-456",
            tool_name="delete_file",
            message="Delete approval",
            required_scopes=["scope1"],
            arguments={"path": "file.txt"},
            context_metadata={"session_id": "sess-2"},
        )
        assert Path(json_path).exists()
        data = json.loads(Path(json_path).read_text())
        assert data["request_id"] == "req-456"
        assert data["tool_name"] == "delete_file"

    def test_cleanup_old_artifacts(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
        gen = ApprovalArtifactGenerator(artifacts_root=str(tmp_path / "arts"))
        gen._max_artifacts = 2
        # Generate 3 artifacts to trigger cleanup
        for i in range(3):
            gen.generate_json_artifact(
                request_id=f"req-{i}",
                tool_name="write_file",
                message="Test",
                required_scopes=["scope1"],
                arguments={},
                context_metadata={},
            )
        # After cleanup, at most 2 artifacts should remain
        artifacts = list(gen.artifacts_root.glob("**/*.json"))
        assert len(artifacts) <= 2

    def test_html_content_escaping(self, tmp_path):
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
        gen = ApprovalArtifactGenerator(artifacts_root=str(tmp_path / "arts"))
        html_path = gen.generate_html_artifact(
            request_id="req-xss",
            tool_name="<script>alert('xss')</script>",
            message="<b>bold</b>",
            required_scopes=["scope&1"],
            arguments={"path": "<malicious>"},
            context_metadata={},
        )
        content = Path(html_path).read_text()
        assert "<script>" not in content
        assert "&lt;script&gt;" in content


def test_get_artifact_generator_singleton(tmp_path, monkeypatch):
    """Test that get_artifact_generator returns a singleton."""
    import src.meta_mcp.governance.artifacts as artifacts_module
    # Reset singleton for test
    artifacts_module._artifact_generator = None
    monkeypatch.setenv("ARTIFACTS_ROOT", str(tmp_path / "test_arts"))

    from src.meta_mcp.governance.artifacts import get_artifact_generator
    gen1 = get_artifact_generator()
    gen2 = get_artifact_generator()
    assert gen1 is gen2

    # Reset singleton after test
    artifacts_module._artifact_generator = None


# ============================================================================
# APPROVAL PROVIDER FACTORY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_factory_auto_selects_fastmcp_elicit():
    """ApprovalProviderFactory.create_provider() auto-selects FastMCPElicitProvider with context."""
    from src.meta_mcp.governance.approval import (
        ApprovalProviderFactory,
        FastMCPElicitProvider,
    )
    ctx = MagicMock()
    ctx.elicit = MagicMock()
    provider = await ApprovalProviderFactory.create_provider(context=ctx)
    assert isinstance(provider, FastMCPElicitProvider)


@pytest.mark.asyncio
async def test_factory_explicit_fastmcp_provider(monkeypatch):
    """ApprovalProviderFactory.create_provider() with explicit fastmcp_elicit."""
    from src.meta_mcp.governance.approval import (
        ApprovalProviderFactory,
        FastMCPElicitProvider,
    )
    ctx = MagicMock()
    ctx.elicit = MagicMock()
    monkeypatch.setenv("APPROVAL_PROVIDER", "fastmcp_elicit")
    provider = await ApprovalProviderFactory.create_provider(context=ctx)
    assert isinstance(provider, FastMCPElicitProvider)


@pytest.mark.asyncio
async def test_factory_explicit_unknown_provider_falls_back(monkeypatch):
    """ApprovalProviderFactory falls back to auto when unknown provider requested."""
    from src.meta_mcp.governance.approval import (
        ApprovalProviderFactory,
        FastMCPElicitProvider,
    )
    ctx = MagicMock()
    ctx.elicit = MagicMock()
    provider = await ApprovalProviderFactory.create_provider(
        provider_name="unknown_provider_xyz", context=ctx
    )
    # Falls back to auto-selection, FastMCPElicitProvider available
    assert isinstance(provider, FastMCPElicitProvider)


@pytest.mark.asyncio
async def test_get_approval_provider_singleton(monkeypatch):
    """get_approval_provider() returns consistent provider for same context."""
    import src.meta_mcp.governance.approval as approval_module
    # Reset singleton
    approval_module._approval_provider = None

    ctx = MagicMock()
    ctx.elicit = MagicMock()

    from src.meta_mcp.governance.approval import (
        FastMCPElicitProvider,
        get_approval_provider,
    )
    provider1 = await get_approval_provider(context=ctx)
    assert isinstance(provider1, FastMCPElicitProvider)

    # Reset for other tests
    approval_module._approval_provider = None


@pytest.mark.asyncio
async def test_dbus_provider_is_available_cached():
    """DBusGUIProvider.is_available() returns cached False on second call."""
    from src.meta_mcp.governance.approval import DBusGUIProvider
    provider = DBusGUIProvider()
    r1 = await provider.is_available()
    r2 = await provider.is_available()
    assert not r1 and not r2  # Cached False (no dasbus)


# ============================================================================
# TOKENS COVERAGE TESTS
# ============================================================================


def test_verify_token_non_canonical_base64():
    """verify_token() rejects non-canonical base64."""
    from src.meta_mcp.governance.tokens import generate_token, verify_token
    # Generate a valid token then tamper with base64
    token = generate_token("client", "tool", 300, "secret_32_bytes_minimum_length!!")
    # Split and corrupt
    parts = token.split(".")
    if len(parts) == 2:
        # Try with a corrupted signature (should fail)
        bad_token = parts[0] + ".badsignature"
        result = verify_token(bad_token, "client", "tool", "secret_32_bytes_minimum_length!!")
        assert result is False


def test_verify_token_valid_roundtrip():
    """verify_token() accepts token generated by generate_token()."""
    from src.meta_mcp.governance.tokens import generate_token, verify_token
    secret = "test_secret_for_roundtrip_testing_32b"
    token = generate_token("client1", "write_file", 300, secret)
    assert verify_token(token, "client1", "write_file", secret) is True


def test_verify_token_wrong_client():
    """verify_token() rejects token with wrong client_id."""
    from src.meta_mcp.governance.tokens import generate_token, verify_token
    secret = "test_secret_wrong_client_checking!!"
    token = generate_token("client1", "write_file", 300, secret)
    assert verify_token(token, "wrong_client", "write_file", secret) is False


def test_verify_token_empty_string():
    """verify_token() handles empty/malformed token."""
    from src.meta_mcp.governance.tokens import verify_token
    assert verify_token("", "client", "tool", "secret") is False
    assert verify_token("no_dot_here", "client", "tool", "secret") is False


def test_decode_token_empty():
    """decode_token() returns None for empty token."""
    from src.meta_mcp.governance.tokens import decode_token
    assert decode_token("") is None
    assert decode_token(None) is None


def test_decode_token_valid():
    """decode_token() returns payload for valid token."""
    from src.meta_mcp.governance.tokens import decode_token, generate_token
    token = generate_token("client1", "write_file", 300, "test_secret_for_decode_32bytesxxxx")
    payload = decode_token(token)
    assert payload is not None
    assert payload["client_id"] == "client1"
    assert payload["tool_id"] == "write_file"


def test_decode_token_bad_base64():
    """decode_token() returns None for malformed base64."""
    from src.meta_mcp.governance.tokens import decode_token
    result = decode_token("!!!invalid_base64!!!.signature")
    assert result is None


def test_decode_token_not_two_parts():
    """decode_token() returns None when token doesn't have exactly two parts."""
    from src.meta_mcp.governance.tokens import decode_token
    assert decode_token("onepart") is None
    assert decode_token("one.two.three") is None
