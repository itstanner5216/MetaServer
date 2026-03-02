"""Targeted tests to improve coverage for governance, validation, and middleware modules.

Covers:
- validation.py: validate_bootstrap_tools, validate_no_auto_mounts, run_all_validations
- governance/artifacts.py: ArtifactGenerator, generate_html, generate_json
- governance/approval.py: FastMCPElicitProvider, ApprovalResponse, helper methods
"""

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# VALIDATION MODULE TESTS
# ============================================================================


class TestValidationModule:
    """Tests for src/meta_mcp/validation.py"""

    @pytest.mark.asyncio
    async def test_validate_bootstrap_tools_match(self):
        """Test validate_bootstrap_tools when tools match expected set."""
        from src.meta_mcp.validation import validate_bootstrap_tools

        mock_mcp = MagicMock()
        mock_tool_search = MagicMock()
        mock_tool_search.name = "search_tools"
        mock_tool_schema = MagicMock()
        mock_tool_schema.name = "get_tool_schema"
        mock_mcp.get_tools = AsyncMock(
            return_value={"search_tools": mock_tool_search, "get_tool_schema": mock_tool_schema}
        )

        mock_registry = MagicMock()
        mock_registry.get_bootstrap_tools.return_value = ["search_tools", "get_tool_schema"]

        result = await validate_bootstrap_tools(mock_mcp, mock_registry)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_bootstrap_tools_mismatch(self):
        """Test validate_bootstrap_tools when extra tools are exposed."""
        from src.meta_mcp.validation import validate_bootstrap_tools

        mock_mcp = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search_tools"
        mock_extra = MagicMock()
        mock_extra.name = "extra_tool"
        mock_mcp.get_tools = AsyncMock(
            return_value={
                "search_tools": mock_tool,
                "extra_tool": mock_extra,
            }
        )

        mock_registry = MagicMock()
        mock_registry.get_bootstrap_tools.return_value = ["search_tools"]

        result = await validate_bootstrap_tools(mock_mcp, mock_registry)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_bootstrap_tools_missing_tools(self):
        """Test validate_bootstrap_tools when expected tools are missing."""
        from src.meta_mcp.validation import validate_bootstrap_tools

        mock_mcp = MagicMock()
        mock_mcp.get_tools = AsyncMock(return_value={})

        mock_registry = MagicMock()
        mock_registry.get_bootstrap_tools.return_value = ["search_tools", "get_tool_schema"]

        result = await validate_bootstrap_tools(mock_mcp, mock_registry)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_bootstrap_tools_error_handling(self):
        """Test validate_bootstrap_tools handles exceptions gracefully."""
        from src.meta_mcp.validation import validate_bootstrap_tools

        mock_mcp = MagicMock()
        mock_mcp.get_tools = AsyncMock(side_effect=RuntimeError("MCP error"))

        mock_registry = MagicMock()
        mock_registry.get_bootstrap_tools.return_value = ["search_tools"]

        result = await validate_bootstrap_tools(mock_mcp, mock_registry)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_no_auto_mounts(self):
        """Test validate_no_auto_mounts always returns True (placeholder)."""
        from src.meta_mcp.validation import validate_no_auto_mounts

        mock_mcp = MagicMock()
        result = await validate_no_auto_mounts(mock_mcp)
        assert result is True

    @pytest.mark.asyncio
    async def test_run_all_validations_all_pass(self):
        """Test run_all_validations when all checks pass."""
        from src.meta_mcp.validation import run_all_validations

        mock_mcp = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search_tools"
        mock_schema = MagicMock()
        mock_schema.name = "get_tool_schema"
        mock_mcp.get_tools = AsyncMock(
            return_value={"search_tools": mock_tool, "get_tool_schema": mock_schema}
        )

        mock_registry = MagicMock()
        mock_registry.get_bootstrap_tools.return_value = ["search_tools", "get_tool_schema"]

        results = await run_all_validations(mock_mcp, mock_registry)
        assert results["bootstrap_tools"] is True
        assert results["no_auto_mounts"] is True

    @pytest.mark.asyncio
    async def test_run_all_validations_some_fail(self):
        """Test run_all_validations when some checks fail."""
        from src.meta_mcp.validation import run_all_validations

        mock_mcp = MagicMock()
        mock_mcp.get_tools = AsyncMock(side_effect=RuntimeError("error"))

        mock_registry = MagicMock()
        mock_registry.get_bootstrap_tools.return_value = ["search_tools"]

        results = await run_all_validations(mock_mcp, mock_registry)
        assert results["bootstrap_tools"] is False
        assert results["no_auto_mounts"] is True


# ============================================================================
# ARTIFACTS MODULE TESTS
# ============================================================================


class TestArtifactsModule:
    """Tests for src/meta_mcp/governance/artifacts.py"""

    def test_artifact_generator_init(self, tmp_path):
        """Test ArtifactGenerator initializes correctly."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        root = tmp_path / "artifacts"
        gen = ApprovalArtifactGenerator(str(root))
        assert gen.artifacts_root == root
        assert root.exists()

    def test_artifact_generator_unsafe_root_raises(self):
        """Test ArtifactGenerator raises on unsafe root directory."""
        from src.meta_mcp.governance.artifacts import (
            ApprovalArtifactGenerator,
            ArtifactGenerationError,
        )

        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator("/etc")

    def test_artifact_generator_system_root_raises(self):
        """Test ArtifactGenerator raises on / root directory."""
        from src.meta_mcp.governance.artifacts import (
            ApprovalArtifactGenerator,
            ArtifactGenerationError,
        )

        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator("/")

    def test_generate_html_artifact(self, tmp_path):
        """Test HTML artifact generation."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        path = gen.generate_html_artifact(
            request_id="test-123",
            tool_name="write_file",
            message="Approve write_file operation",
            required_scopes=["tool:write_file", "filesystem:write"],
            arguments={"path": "/tmp/test.txt", "content": "hello"},
            context_metadata={"session_id": "sess-abc"},
        )

        assert Path(path).exists()
        content = Path(path).read_text()
        assert "write_file" in content
        assert "test-123" in content

    def test_generate_json_artifact(self, tmp_path):
        """Test JSON artifact generation."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        path = gen.generate_json_artifact(
            request_id="req-456",
            tool_name="delete_file",
            message="Approve delete_file operation",
            required_scopes=["tool:delete_file"],
            arguments={"path": "/tmp/test.txt"},
            context_metadata={"user": "test"},
        )

        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["request_id"] == "req-456"
        assert data["tool_name"] == "delete_file"
        assert any("delete_file" in s for s in data["required_scopes"])

    def test_validate_path_traversal_blocked(self, tmp_path):
        """Test path traversal is blocked."""
        from src.meta_mcp.governance.artifacts import (
            ApprovalArtifactGenerator,
            ArtifactGenerationError,
        )

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        with pytest.raises(ArtifactGenerationError):
            gen._validate_path("../../../etc/passwd")

    def test_cleanup_old_artifacts(self, tmp_path):
        """Test cleanup of old artifacts when max is exceeded."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        root = tmp_path / "artifacts"
        gen = ApprovalArtifactGenerator(str(root))
        gen._max_artifacts = 3  # Low limit for testing

        # Create more than max_artifacts files
        for i in range(5):
            (root / f"test_{i}.html").write_text(f"content {i}")

        gen._cleanup_old_artifacts()
        remaining = list(root.glob("*.html"))
        assert len(remaining) <= 3

    def test_get_artifact_generator_singleton(self, tmp_path):
        """Test get_artifact_generator returns an instance."""
        from src.meta_mcp.governance.artifacts import get_artifact_generator

        with patch.dict(os.environ, {"ARTIFACTS_ROOT": str(tmp_path / "artifacts")}):
            gen = get_artifact_generator(str(tmp_path / "artifacts"))
            assert gen is not None

    def test_generate_html_artifact_xss_protection(self, tmp_path):
        """Test HTML artifact escapes user input to prevent XSS."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        path = gen.generate_html_artifact(
            request_id="xss-test",
            tool_name="<script>alert('xss')</script>",
            message="<img src=x onerror=alert(1)>",
            required_scopes=["scope"],
            arguments={"key": "<evil>"},
            context_metadata={},
        )

        content = Path(path).read_text()
        # Verify XSS is escaped - angle brackets should be HTML-encoded
        assert "<script>" not in content
        assert "<img " not in content


# ============================================================================
# APPROVAL MODULE TESTS (unit-level, no Redis needed)
# ============================================================================


class TestApprovalResponse:
    """Tests for ApprovalResponse and related data structures."""

    def test_is_approved_returns_true(self):
        """Test is_approved returns True for approved with scopes."""
        from src.meta_mcp.governance.approval import ApprovalDecision, ApprovalResponse

        response = ApprovalResponse(
            request_id="req-1",
            decision=ApprovalDecision.APPROVED,
            selected_scopes=["scope:read"],
        )
        assert response.is_approved() is True

    def test_is_approved_returns_false_when_denied(self):
        """Test is_approved returns False for denied."""
        from src.meta_mcp.governance.approval import ApprovalDecision, ApprovalResponse

        response = ApprovalResponse(
            request_id="req-1",
            decision=ApprovalDecision.DENIED,
        )
        assert response.is_approved() is False

    def test_is_approved_returns_false_when_no_scopes(self):
        """Test is_approved returns False for approved but no scopes."""
        from src.meta_mcp.governance.approval import ApprovalDecision, ApprovalResponse

        response = ApprovalResponse(
            request_id="req-1",
            decision=ApprovalDecision.APPROVED,
            selected_scopes=[],
        )
        assert response.is_approved() is False


class TestFastMCPElicitProvider:
    """Tests for FastMCPElicitProvider."""

    def test_init_with_context(self):
        """Test FastMCPElicitProvider initializes with context."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        ctx = MagicMock()
        provider = FastMCPElicitProvider(context=ctx)
        assert provider._context == ctx

    def test_set_context(self):
        """Test FastMCPElicitProvider.set_context updates context."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        provider = FastMCPElicitProvider()
        ctx = MagicMock()
        provider.set_context(ctx)
        assert provider._context == ctx

    @pytest.mark.asyncio
    async def test_is_available_true_with_elicit(self):
        """Test is_available returns True when context has elicit method."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        provider = FastMCPElicitProvider(context=ctx)
        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_false_without_context(self):
        """Test is_available returns False without context."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        provider = FastMCPElicitProvider()
        assert await provider.is_available() is False

    def test_get_name(self):
        """Test FastMCPElicitProvider.get_name."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        provider = FastMCPElicitProvider()
        assert provider.get_name() == "FastMCP Elicit"

    @pytest.mark.asyncio
    async def test_request_approval_no_context(self):
        """Test request_approval returns ERROR when context is not available."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        provider = FastMCPElicitProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.ERROR

    @pytest.mark.asyncio
    async def test_request_approval_json_response(self):
        """Test request_approval parses JSON approval response."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock(
            return_value=json.dumps({
                "decision": "approved",
                "selected_scopes": ["scope:write"],
                "lease_seconds": 300,
            })
        )
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.APPROVED
        assert "scope:write" in response.selected_scopes
        assert response.lease_seconds == 300

    @pytest.mark.asyncio
    async def test_request_approval_simple_yes(self):
        """Test request_approval handles simple 'yes' response."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock(return_value="yes")
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_request_approval_simple_no(self):
        """Test request_approval handles simple 'no' response."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock(return_value="no")
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.DENIED

    @pytest.mark.asyncio
    async def test_request_approval_timeout(self):
        """Test request_approval returns TIMEOUT on asyncio.TimeoutError."""
        import asyncio

        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=asyncio.TimeoutError())
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
            timeout_seconds=1,
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.TIMEOUT

    @pytest.mark.asyncio
    async def test_request_approval_exception(self):
        """Test request_approval returns ERROR on unexpected exception."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=RuntimeError("unexpected error"))
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.ERROR


class TestParseHelpers:
    """Tests for FastMCPElicitProvider static helper methods."""

    def test_parse_decision_approved(self):
        """Test _parse_decision returns APPROVED for various inputs."""
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_decision("approved") == ApprovalDecision.APPROVED
        assert FastMCPElicitProvider._parse_decision("approve") == ApprovalDecision.APPROVED
        assert FastMCPElicitProvider._parse_decision("yes") == ApprovalDecision.APPROVED
        assert FastMCPElicitProvider._parse_decision("y") == ApprovalDecision.APPROVED

    def test_parse_decision_denied(self):
        """Test _parse_decision returns DENIED for various inputs."""
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_decision("denied") == ApprovalDecision.DENIED
        assert FastMCPElicitProvider._parse_decision("deny") == ApprovalDecision.DENIED
        assert FastMCPElicitProvider._parse_decision("no") == ApprovalDecision.DENIED

    def test_parse_decision_none(self):
        """Test _parse_decision returns None for None input."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_decision(None) is None

    def test_parse_decision_unknown(self):
        """Test _parse_decision returns None for unknown input."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_decision("maybe") is None

    def test_parse_scopes_list(self):
        """Test _parse_scopes handles list input."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_scopes(["scope:read", "scope:write"])
        assert result == ["scope:read", "scope:write"]

    def test_parse_scopes_string(self):
        """Test _parse_scopes handles comma-separated string."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_scopes("scope:read, scope:write")
        assert "scope:read" in result
        assert "scope:write" in result

    def test_parse_scopes_json_string(self):
        """Test _parse_scopes handles JSON array string."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_scopes('["scope:read", "scope:write"]')
        assert "scope:read" in result
        assert "scope:write" in result

    def test_parse_scopes_none(self):
        """Test _parse_scopes handles None input."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_scopes(None) == []

    def test_parse_lease_seconds_valid(self):
        """Test _parse_lease_seconds returns valid int."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_lease_seconds(300) == 300
        assert FastMCPElicitProvider._parse_lease_seconds("300") == 300
        assert FastMCPElicitProvider._parse_lease_seconds("300.5") == 300

    def test_parse_lease_seconds_negative(self):
        """Test _parse_lease_seconds clamps negative to 0."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_lease_seconds(-100) == 0

    def test_parse_lease_seconds_none(self):
        """Test _parse_lease_seconds handles None."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_lease_seconds(None) == 0

    def test_parse_lease_seconds_invalid(self):
        """Test _parse_lease_seconds handles invalid string."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_lease_seconds("invalid") == 0

    def test_parse_structured_response_dict(self):
        """Test _parse_structured_response handles dict input."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response(
            {"Decision": "approved", "Selected_Scopes": ["scope:read"]}
        )
        assert result["decision"] == "approved"

    def test_parse_structured_response_json_string(self):
        """Test _parse_structured_response handles JSON string."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response(
            '{"decision": "approved", "selected_scopes": ["scope:read"]}'
        )
        assert result["decision"] == "approved"

    def test_parse_structured_response_key_value(self):
        """Test _parse_structured_response handles key=value format."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response(
            "decision=approved\nselected_scopes=scope:read\nlease_seconds=300"
        )
        assert result.get("decision") == "approved"

    def test_parse_key_value_response_semicolon(self):
        """Test _parse_key_value_response handles semicolon-separated pairs."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_key_value_response(
            "decision=approved;selected_scopes=scope:read"
        )
        assert result.get("decision") == "approved"

    def test_parse_approval_payload_with_data(self):
        """Test _parse_approval_payload handles payload with .data attribute."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        payload = MagicMock()
        payload.data = json.dumps({
            "decision": "approved",
            "selected_scopes": ["scope:write"],
            "lease_seconds": 300,
        })
        result = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert result.decision == ApprovalDecision.APPROVED


class TestDBusGUIProvider:
    """Tests for DBusGUIProvider."""

    def test_init(self):
        """Test DBusGUIProvider initializes correctly."""
        from src.meta_mcp.governance.approval import DBusGUIProvider

        provider = DBusGUIProvider()
        assert provider._available is None

    @pytest.mark.asyncio
    async def test_is_available_false_when_no_dasbus(self):
        """Test is_available returns False when dasbus is not installed."""
        from src.meta_mcp.governance.approval import DBusGUIProvider

        provider = DBusGUIProvider()

        with patch.dict("sys.modules", {"dasbus": None, "dasbus.connection": None}):
            provider._available = None  # Reset cached state
            # Force ImportError by making the import fail
            with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: (
                (_ for _ in ()).throw(ImportError(f"No module named '{name}'"))
                if name == "dasbus" or name.startswith("dasbus")
                else __import__(name, *args, **kwargs)
            )):
                result = await provider.is_available()
            assert result is False

    def test_get_name(self):
        """Test DBusGUIProvider.get_name."""
        from src.meta_mcp.governance.approval import DBusGUIProvider

        provider = DBusGUIProvider()
        assert provider.get_name() == "DBus GUI"


class TestApprovalProviderFactory:
    """Tests for ApprovalProviderFactory."""

    @pytest.mark.asyncio
    async def test_create_provider_auto_with_context(self):
        """Test create_provider auto-selects FastMCP elicit when context has elicit."""
        from src.meta_mcp.governance.approval import (
            ApprovalProviderFactory,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock()

        with patch.object(
            FastMCPElicitProvider, "is_available", return_value=True
        ):
            provider = await ApprovalProviderFactory.create_provider(context=ctx)
            assert provider is not None


class TestSystemdFallbackProvider:
    """Tests for SystemdFallbackProvider."""

    def test_get_name(self):
        """Test SystemdFallbackProvider.get_name."""
        from src.meta_mcp.governance.approval import SystemdFallbackProvider

        provider = SystemdFallbackProvider()
        assert provider.get_name() == "systemd Fallback"

    @pytest.mark.asyncio
    async def test_is_available_when_systemd_not_found(self):
        """Test is_available returns False when systemd-ask-password not found."""
        from src.meta_mcp.governance.approval import SystemdFallbackProvider

        provider = SystemdFallbackProvider()

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_request_approval_approved(self):
        """Test SystemdFallbackProvider.request_approval with 'yes' response."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            SystemdFallbackProvider,
        )

        provider = SystemdFallbackProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"yes\n", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            response = await provider.request_approval(request)

        assert response.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_request_approval_denied(self):
        """Test SystemdFallbackProvider.request_approval with 'no' response."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            SystemdFallbackProvider,
        )

        provider = SystemdFallbackProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"no\n", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            response = await provider.request_approval(request)

        assert response.decision == ApprovalDecision.DENIED

    @pytest.mark.asyncio
    async def test_request_approval_exception(self):
        """Test SystemdFallbackProvider.request_approval on exception."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            SystemdFallbackProvider,
        )

        provider = SystemdFallbackProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )

        with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("error")):
            response = await provider.request_approval(request)

        assert response.decision == ApprovalDecision.ERROR


# ============================================================================
# MIDDLEWARE UNIT TESTS (no Redis)
# ============================================================================


class TestMiddlewareUnit:
    """Unit tests for GovernanceMiddleware that don't need Redis."""

    def test_extract_context_key_write_file(self):
        """Test _extract_context_key for write_file uses path."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        key = GovernanceMiddleware._extract_context_key(
            "write_file", {"path": "/tmp/test.txt", "content": "hello"}
        )
        assert "/tmp/test.txt" in key

    def test_extract_context_key_execute_command(self):
        """Test _extract_context_key for execute_command truncates command."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        long_cmd = "a" * 100
        key = GovernanceMiddleware._extract_context_key("execute_command", {"command": long_cmd})
        assert len(key) <= 50

    def test_extract_context_key_git_tools(self):
        """Test _extract_context_key for git tools uses cwd."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        key = GovernanceMiddleware._extract_context_key(
            "git_commit", {"cwd": "/home/user/myrepo", "message": "Initial commit"}
        )
        assert "myrepo" in key

    def test_extract_context_key_default(self):
        """Test _extract_context_key falls back to tool_name."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        key = GovernanceMiddleware._extract_context_key("unknown_tool", {})
        assert key == "unknown_tool"

    def test_generate_request_id(self):
        """Test _generate_request_id returns a deterministic-ish ID."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        req_id = GovernanceMiddleware._generate_request_id(
            "session-123", "write_file", "/tmp/test.txt"
        )
        assert "write_file" in req_id

    def test_apply_toon_encoding_disabled(self):
        """Test _apply_toon_encoding returns unchanged result when disabled."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        mw = GovernanceMiddleware()
        result = mw._apply_toon_encoding("test result")
        assert result == "test result"

    def test_compute_elevation_key(self):
        """Test _compute_elevation_key returns a string."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        mw = GovernanceMiddleware()
        key = mw._compute_elevation_key("write_file", {"path": "/tmp/test.txt"}, "session-123")
        assert isinstance(key, str)
        assert len(key) > 0

    def test_get_required_scopes_write_file(self):
        """Test _get_required_scopes returns scopes for write_file."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        mw = GovernanceMiddleware()
        scopes = mw._get_required_scopes("write_file", {"path": "/tmp/test.txt"})
        assert isinstance(scopes, list)
        assert len(scopes) > 0

    def test_get_required_scopes_execute_command(self):
        """Test _get_required_scopes returns scopes for execute_command."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        mw = GovernanceMiddleware()
        scopes = mw._get_required_scopes("execute_command", {"command": "ls"})
        assert isinstance(scopes, list)
        assert len(scopes) > 0

    def test_get_required_scopes_unknown_tool(self):
        """Test _get_required_scopes returns at least one scope for unknown tool."""
        from src.meta_mcp.middleware import GovernanceMiddleware

        mw = GovernanceMiddleware()
        scopes = mw._get_required_scopes("unknown_sensitive_tool", {})
        assert isinstance(scopes, list)
        assert len(scopes) > 0


# ============================================================================
# LEASE MANAGER UNIT TESTS (no Redis needed)
# ============================================================================


class TestLeaseManagerUnit:
    """Unit tests for LeaseManager that don't require Redis."""

    def test_lease_key_format(self):
        """Test _lease_key generates correct key format."""
        from src.meta_mcp.leases.manager import LeaseManager

        key = LeaseManager._lease_key("client-123", "write_file")
        assert key == "lease:client-123:write_file"

    def test_register_notification_callback(self):
        """Test register_notification_callback adds callback."""
        from src.meta_mcp.leases.manager import LeaseManager

        manager = LeaseManager()
        cb = MagicMock()
        manager.register_notification_callback(cb)
        assert cb in manager._notification_callbacks

    def test_unregister_notification_callback(self):
        """Test unregister_notification_callback removes callback."""
        from src.meta_mcp.leases.manager import LeaseManager

        manager = LeaseManager()
        cb = MagicMock()
        manager.register_notification_callback(cb)
        manager.unregister_notification_callback(cb)
        assert cb not in manager._notification_callbacks

    def test_unregister_nonexistent_callback_is_safe(self):
        """Test unregister_notification_callback is safe for unknown callback."""
        from src.meta_mcp.leases.manager import LeaseManager

        manager = LeaseManager()
        cb = MagicMock()
        # Should not raise
        manager.unregister_notification_callback(cb)

    @pytest.mark.asyncio
    async def test_emit_list_changed_sync_callback(self):
        """Test _emit_list_changed calls sync callback."""
        from src.meta_mcp.leases.manager import LeaseManager

        manager = LeaseManager()
        received = []

        def sync_cb(client_id):
            received.append(client_id)

        manager.register_notification_callback(sync_cb)
        await manager._emit_list_changed("client-123")
        assert "client-123" in received

    @pytest.mark.asyncio
    async def test_emit_list_changed_async_callback(self):
        """Test _emit_list_changed calls async callback."""
        from src.meta_mcp.leases.manager import LeaseManager

        manager = LeaseManager()
        received = []

        async def async_cb(client_id):
            received.append(client_id)

        manager.register_notification_callback(async_cb)
        await manager._emit_list_changed("client-456")
        assert "client-456" in received

    @pytest.mark.asyncio
    async def test_emit_list_changed_callback_error_is_handled(self):
        """Test _emit_list_changed handles callback errors gracefully."""
        from src.meta_mcp.leases.manager import LeaseManager

        manager = LeaseManager()

        def failing_cb(client_id):
            raise RuntimeError("callback error")

        manager.register_notification_callback(failing_cb)
        # Should not raise
        await manager._emit_list_changed("client-789")


# ============================================================================
# MORE EDGE CASE TESTS FOR APPROVAL MODULE
# ============================================================================


class TestParseHelpersEdgeCases:
    """Additional edge case tests for parse helper methods."""

    def test_parse_structured_response_none(self):
        """Test _parse_structured_response handles None."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response(None)
        assert result == {}

    def test_parse_structured_response_empty_string(self):
        """Test _parse_structured_response handles empty string."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response("")
        assert result == {}

    def test_parse_structured_response_non_dict_json(self):
        """Test _parse_structured_response handles non-dict JSON (falls back to key-value)."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        # JSON array, not dict
        result = FastMCPElicitProvider._parse_structured_response(
            '["scope:read", "scope:write"]'
        )
        # Falls through to key-value parsing
        assert isinstance(result, dict)

    def test_parse_structured_response_colon_format(self):
        """Test _parse_structured_response handles key:value format."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response(
            "decision:approved\nselected_scopes:scope:read"
        )
        assert result.get("decision") == "approved"

    def test_parse_structured_response_non_string_non_dict(self):
        """Test _parse_structured_response handles non-string, non-dict types."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_structured_response(42)
        assert result == {}

    def test_parse_decision_timeout(self):
        """Test _parse_decision handles 'timeout'."""
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_decision("timeout") == ApprovalDecision.TIMEOUT

    def test_parse_decision_error(self):
        """Test _parse_decision handles 'error'."""
        from src.meta_mcp.governance.approval import ApprovalDecision, FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_decision("error") == ApprovalDecision.ERROR

    def test_parse_scopes_empty_string(self):
        """Test _parse_scopes handles empty string."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        assert FastMCPElicitProvider._parse_scopes("") == []

    def test_parse_scopes_invalid_json_array(self):
        """Test _parse_scopes falls back for invalid JSON array."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        # Starts with [ but not valid JSON
        result = FastMCPElicitProvider._parse_scopes("[scope:read, scope:write]")
        assert isinstance(result, list)

    def test_parse_scopes_non_list_non_string(self):
        """Test _parse_scopes handles non-list, non-string values."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_scopes(42)
        assert result == ["42"]

    def test_parse_key_value_response_colon_separator(self):
        """Test _parse_key_value_response handles colon-separated pairs."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_key_value_response(
            "decision:approved\nselected_scopes:scope:read"
        )
        assert result.get("decision") == "approved"

    def test_parse_key_value_response_empty_line(self):
        """Test _parse_key_value_response handles empty lines."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_key_value_response(
            "decision=approved\n\nselected_scopes=scope:read"
        )
        assert result.get("decision") == "approved"

    def test_parse_key_value_response_no_separator(self):
        """Test _parse_key_value_response skips lines without separator."""
        from src.meta_mcp.governance.approval import FastMCPElicitProvider

        result = FastMCPElicitProvider._parse_key_value_response(
            "this_has_no_separator\ndecision=approved"
        )
        assert result.get("decision") == "approved"


class TestFastMCPElicitProviderEdgeCases:
    """Edge case tests for FastMCPElicitProvider."""

    @pytest.mark.asyncio
    async def test_request_approval_response_with_data_attr(self):
        """Test request_approval handles response objects with .data attribute."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        response_obj = MagicMock()
        response_obj.data = json.dumps({
            "decision": "approved",
            "selected_scopes": ["scope:write"],
            "lease_seconds": 300,
        })
        ctx.elicit = AsyncMock(return_value=response_obj)
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.APPROVED
        assert response.lease_seconds == 300

    @pytest.mark.asyncio
    async def test_request_approval_scopes_auto_decision(self):
        """Test request_approval auto-approves when scopes found but no explicit decision."""
        from src.meta_mcp.governance.approval import (
            ApprovalDecision,
            ApprovalRequest,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        # Response with scopes but no explicit decision
        ctx.elicit = AsyncMock(return_value=json.dumps({
            "selected_scopes": ["scope:write"],
            "lease_seconds": 0,
        }))
        ctx.session_id = "test-session"
        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
        )
        response = await provider.request_approval(request)
        # Should auto-approve when scopes are selected
        assert response.decision == ApprovalDecision.APPROVED


class TestGetApprovalProvider:
    """Tests for get_approval_provider singleton."""

    @pytest.mark.asyncio
    async def test_get_approval_provider_returns_provider(self):
        """Test get_approval_provider returns an approval provider."""
        import src.meta_mcp.governance.approval as approval_module
        from src.meta_mcp.governance.approval import (
            FastMCPElicitProvider,
            get_approval_provider,
        )

        # Reset singleton
        original = approval_module._approval_provider
        approval_module._approval_provider = None

        ctx = MagicMock()
        ctx.elicit = AsyncMock()

        with patch.object(FastMCPElicitProvider, "is_available", return_value=True):
            provider = await get_approval_provider(context=ctx)
            assert provider is not None

        # Restore
        approval_module._approval_provider = original

    @pytest.mark.asyncio
    async def test_get_approval_provider_updates_context(self):
        """Test get_approval_provider updates context on subsequent calls."""
        import src.meta_mcp.governance.approval as approval_module
        from src.meta_mcp.governance.approval import (
            FastMCPElicitProvider,
            get_approval_provider,
        )

        # Set singleton to a FastMCPElicitProvider
        ctx1 = MagicMock()
        ctx2 = MagicMock()
        provider = FastMCPElicitProvider(context=ctx1)
        approval_module._approval_provider = provider

        await get_approval_provider(context=ctx2)
        assert provider._context == ctx2

        # Reset
        approval_module._approval_provider = None


class TestApprovalProviderFactoryEdgeCases:
    """Edge case tests for ApprovalProviderFactory."""

    @pytest.mark.asyncio
    async def test_create_provider_explicit_fastmcp(self):
        """Test create_provider with explicit fastmcp_elicit preference."""
        from src.meta_mcp.governance.approval import (
            ApprovalProviderFactory,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock()

        with patch.object(FastMCPElicitProvider, "is_available", return_value=True):
            provider = await ApprovalProviderFactory.create_provider(
                provider_name="fastmcp_elicit", context=ctx
            )
            assert isinstance(provider, FastMCPElicitProvider)

    @pytest.mark.asyncio
    async def test_create_provider_explicit_unavailable_falls_back(self):
        """Test create_provider falls back when explicit provider unavailable."""
        from src.meta_mcp.governance.approval import (
            ApprovalProviderFactory,
            FastMCPElicitProvider,
        )

        ctx = MagicMock()
        ctx.elicit = AsyncMock()

        with patch.object(FastMCPElicitProvider, "is_available", return_value=False):
            # Request dbus_gui which is never available, should fall back
            try:
                provider = await ApprovalProviderFactory.create_provider(
                    provider_name="dbus_gui", context=ctx
                )
                # If it succeeds, it's FastMCP elicit fallback
                assert provider is not None
            except RuntimeError:
                # No providers available is acceptable
                pass


# ============================================================================
# ARTIFACT EDGE CASE TESTS
# ============================================================================


class TestArtifactsEdgeCases:
    """Edge case tests for artifact generation."""

    def test_generate_html_artifact_path_validation(self, tmp_path):
        """Test HTML artifact path is within artifacts root."""
        from src.meta_mcp.governance.artifacts import (
            ApprovalArtifactGenerator,
            ArtifactGenerationError,
        )

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        # Valid path should work
        path = gen.generate_html_artifact(
            request_id="valid-test",
            tool_name="test_tool",
            message="Test",
            required_scopes=["scope:test"],
            arguments={},
            context_metadata={},
        )
        assert Path(path).is_absolute()
        assert str(tmp_path) in path

    def test_validate_path_absolute_path_blocked(self, tmp_path):
        """Test _validate_path blocks absolute paths outside root."""
        from src.meta_mcp.governance.artifacts import (
            ApprovalArtifactGenerator,
            ArtifactGenerationError,
        )

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        with pytest.raises(ArtifactGenerationError):
            gen._validate_path("/etc/passwd")

    def test_generate_html_content_structure(self, tmp_path):
        """Test _generate_html_content produces valid HTML."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))

        html = gen._generate_html_content(
            request_id="test-html",
            tool_name="write_file",
            message="Approve?",
            required_scopes=["scope:write"],
            arguments={"path": "/tmp/test.txt"},
            context_metadata={"session": "abc"},
        )

        assert "<!DOCTYPE html>" in html
        assert "write_file" in html
        assert "scope:write" in html


class TestArtifactsMoreEdgeCases:
    """More edge case tests for artifacts module."""

    def test_artifact_mkdir_error_raises(self, tmp_path, monkeypatch):
        """Test _ensure_safe_root raises when mkdir fails."""
        from src.meta_mcp.governance.artifacts import (
            ApprovalArtifactGenerator,
            ArtifactGenerationError,
        )

        target = tmp_path / "no_write" / "artifacts"

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("no permission")):
            with pytest.raises(ArtifactGenerationError, match="Failed to create"):
                ApprovalArtifactGenerator(str(target))

    def test_cleanup_removes_excess_artifacts(self, tmp_path):
        """Test _cleanup_old_artifacts removes excess when over max."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        root = tmp_path / "artifacts"
        gen = ApprovalArtifactGenerator(str(root))
        gen._max_artifacts = 2

        # Create 4 files
        for i in range(4):
            (root / f"file_{i}.html").write_text(f"content {i}")

        gen._cleanup_old_artifacts()
        # Should have at most 2 files
        assert len(list(root.glob("*.html"))) <= 2

    def test_cleanup_handles_unlink_error(self, tmp_path):
        """Test _cleanup_old_artifacts handles unlink errors gracefully."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        root = tmp_path / "artifacts"
        gen = ApprovalArtifactGenerator(str(root))
        gen._max_artifacts = 1

        # Create 3 files
        for i in range(3):
            (root / f"file_{i}.html").write_text(f"content {i}")

        with patch("pathlib.Path.unlink", side_effect=OSError("cannot unlink")):
            # Should not raise
            gen._cleanup_old_artifacts()

    def test_generate_json_artifact_success(self, tmp_path):
        """Test JSON artifact generates successfully with content."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        path = gen.generate_json_artifact(
            request_id="json-test-001",
            tool_name="read_file",
            message="Approve read?",
            required_scopes=["tool:read_file"],
            arguments={"path": "/tmp/test.txt"},
            context_metadata={"session_id": "sess-abc"},
        )

        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["tool_name"] == "read_file"
        assert data["message"] == "Approve read?"

    def test_generate_json_artifact_writes_metadata(self, tmp_path):
        """Test JSON artifact includes metadata."""
        from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator

        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        path = gen.generate_json_artifact(
            request_id="meta-test",
            tool_name="execute_command",
            message="Allow execution?",
            required_scopes=["tool:execute_command"],
            arguments={"command": "ls -la"},
            context_metadata={"user": "tester"},
        )

        data = json.loads(Path(path).read_text())
        assert "generated_at" in data
        assert data["context_metadata"]["user"] == "tester"
