"""Tests for governance approval module coverage.

Covers ApprovalResponse, FastMCPElicitProvider, SystemdFallbackProvider,
ApprovalProviderFactory, and parsing helpers.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.meta_mcp.governance.approval import (
    ApprovalDecision,
    ApprovalProviderFactory,
    ApprovalRequest,
    ApprovalResponse,
    DBusGUIProvider,
    FastMCPElicitProvider,
    SystemdFallbackProvider,
    get_approval_provider,
)


# ============================================================================
# ApprovalResponse tests
# ============================================================================


class TestApprovalResponse:
    def test_is_approved_with_scopes(self):
        resp = ApprovalResponse(
            request_id="r1",
            decision=ApprovalDecision.APPROVED,
            selected_scopes=["read"],
        )
        assert resp.is_approved() is True

    def test_is_approved_no_scopes(self):
        resp = ApprovalResponse(
            request_id="r1",
            decision=ApprovalDecision.APPROVED,
            selected_scopes=[],
        )
        assert resp.is_approved() is False

    def test_is_approved_denied(self):
        resp = ApprovalResponse(
            request_id="r1",
            decision=ApprovalDecision.DENIED,
            selected_scopes=["read"],
        )
        assert resp.is_approved() is False

    def test_is_approved_timeout(self):
        resp = ApprovalResponse(
            request_id="r1",
            decision=ApprovalDecision.TIMEOUT,
        )
        assert resp.is_approved() is False

    def test_is_approved_error(self):
        resp = ApprovalResponse(
            request_id="r1",
            decision=ApprovalDecision.ERROR,
            error_message="something went wrong",
        )
        assert resp.is_approved() is False


# ============================================================================
# DBusGUIProvider tests
# ============================================================================


class TestDBusGUIProvider:
    @pytest.mark.asyncio
    async def test_is_available_no_dasbus(self):
        provider = DBusGUIProvider()
        with patch.dict("sys.modules", {"dasbus": None, "dasbus.connection": None}):
            provider._available = None
            result = await provider.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_available_cached_true(self):
        provider = DBusGUIProvider()
        provider._available = True
        result = await provider.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_cached_false(self):
        provider = DBusGUIProvider()
        provider._available = False
        result = await provider.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_available_exception(self):
        provider = DBusGUIProvider()
        provider._available = None
        with patch(
            "src.meta_mcp.governance.approval.DBusGUIProvider.is_available",
            new_callable=AsyncMock,
            return_value=False,
        ):
            # Reset for a real test
            pass
        # Just test the error path directly
        provider._available = None
        result = await provider.is_available()
        # Without dasbus installed, should return False
        assert result is False

    def test_get_name(self):
        provider = DBusGUIProvider()
        assert provider.get_name() == "DBus GUI"

    @pytest.mark.asyncio
    async def test_request_approval_no_dasbus(self):
        provider = DBusGUIProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        response = await provider.request_approval(request)
        assert response.decision == ApprovalDecision.ERROR
        assert response.request_id == "req-1"


# ============================================================================
# FastMCPElicitProvider tests
# ============================================================================


class TestFastMCPElicitProvider:
    def test_init_no_context(self):
        provider = FastMCPElicitProvider()
        assert provider._context is None

    def test_init_with_context(self):
        ctx = MagicMock()
        provider = FastMCPElicitProvider(context=ctx)
        assert provider._context is ctx

    def test_set_context(self):
        provider = FastMCPElicitProvider()
        ctx = MagicMock()
        provider.set_context(ctx)
        assert provider._context is ctx

    @pytest.mark.asyncio
    async def test_is_available_no_context(self):
        provider = FastMCPElicitProvider()
        assert await provider.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_no_elicit(self):
        ctx = MagicMock(spec=[])
        provider = FastMCPElicitProvider(context=ctx)
        assert await provider.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_with_elicit(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        provider = FastMCPElicitProvider(context=ctx)
        assert await provider.is_available() is True

    def test_get_name(self):
        provider = FastMCPElicitProvider()
        assert provider.get_name() == "FastMCP Elicit"

    @pytest.mark.asyncio
    async def test_request_approval_no_context(self):
        provider = FastMCPElicitProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.ERROR
        assert "not available" in resp.error_message

    @pytest.mark.asyncio
    async def test_request_approval_json_response(self):
        ctx = MagicMock()
        result = MagicMock()
        result.data = json.dumps({
            "decision": "approved",
            "selected_scopes": ["write"],
            "lease_seconds": 300,
        })
        ctx.elicit = AsyncMock(return_value=result)

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-2",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.APPROVED
        assert resp.selected_scopes == ["write"]
        assert resp.lease_seconds == 300

    @pytest.mark.asyncio
    async def test_request_approval_simple_yes(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock(return_value="yes")

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-3",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.APPROVED
        assert resp.selected_scopes == ["write"]

    @pytest.mark.asyncio
    async def test_request_approval_simple_no(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock(return_value="no")

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-4",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.DENIED

    @pytest.mark.asyncio
    async def test_request_approval_timeout(self):
        ctx = MagicMock()

        async def slow_elicit(*args, **kwargs):
            await asyncio.sleep(10)

        ctx.elicit = AsyncMock(side_effect=slow_elicit)

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-5",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
            timeout_seconds=0,  # instant timeout
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.TIMEOUT

    @pytest.mark.asyncio
    async def test_request_approval_exception(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=RuntimeError("boom"))

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-6",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.ERROR
        assert "boom" in resp.error_message

    @pytest.mark.asyncio
    async def test_request_approval_key_value_response(self):
        ctx = MagicMock()
        result = MagicMock()
        result.data = "decision=approved\nselected_scopes=write,read\nlease_seconds=600"
        ctx.elicit = AsyncMock(return_value=result)

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-7",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write", "read"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.APPROVED
        assert "write" in resp.selected_scopes
        assert resp.lease_seconds == 600

    @pytest.mark.asyncio
    async def test_request_approval_denied_response(self):
        ctx = MagicMock()
        result = MagicMock()
        result.data = json.dumps({
            "decision": "denied",
            "selected_scopes": [],
            "lease_seconds": 0,
        })
        ctx.elicit = AsyncMock(return_value=result)

        provider = FastMCPElicitProvider(context=ctx)
        request = ApprovalRequest(
            request_id="req-8",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        resp = await provider.request_approval(request)
        assert resp.decision == ApprovalDecision.DENIED


# ============================================================================
# Parsing helper tests
# ============================================================================


class TestParsingHelpers:
    def test_parse_structured_response_none(self):
        assert FastMCPElicitProvider._parse_structured_response(None) == {}

    def test_parse_structured_response_dict(self):
        result = FastMCPElicitProvider._parse_structured_response(
            {"Decision": "approved", "Scopes": ["r"]}
        )
        assert result["decision"] == "approved"
        assert result["scopes"] == ["r"]

    def test_parse_structured_response_empty_string(self):
        assert FastMCPElicitProvider._parse_structured_response("") == {}

    def test_parse_structured_response_json_string(self):
        result = FastMCPElicitProvider._parse_structured_response(
            '{"decision": "approved"}'
        )
        assert result["decision"] == "approved"

    def test_parse_structured_response_invalid_json(self):
        result = FastMCPElicitProvider._parse_structured_response(
            "decision=approved; lease_seconds=300"
        )
        assert result["decision"] == "approved"
        assert result["lease_seconds"] == "300"

    def test_parse_structured_response_non_dict_json(self):
        result = FastMCPElicitProvider._parse_structured_response("[1, 2, 3]")
        # Falls through to key-value parsing
        assert isinstance(result, dict)

    def test_parse_structured_response_other_type(self):
        result = FastMCPElicitProvider._parse_structured_response(42)
        assert result == {}

    def test_parse_key_value_response_semicolons(self):
        result = FastMCPElicitProvider._parse_key_value_response(
            "decision=approved;lease_seconds=300"
        )
        assert result["decision"] == "approved"
        assert result["lease_seconds"] == "300"

    def test_parse_key_value_response_newlines(self):
        result = FastMCPElicitProvider._parse_key_value_response(
            "decision=approved\nlease_seconds=300"
        )
        assert result["decision"] == "approved"
        assert result["lease_seconds"] == "300"

    def test_parse_key_value_response_colons(self):
        result = FastMCPElicitProvider._parse_key_value_response(
            "decision:approved\nlease_seconds:300"
        )
        assert result["decision"] == "approved"
        assert result["lease_seconds"] == "300"

    def test_parse_key_value_response_empty_lines(self):
        result = FastMCPElicitProvider._parse_key_value_response(
            "\n\ndecision=approved\n\n"
        )
        assert result["decision"] == "approved"

    def test_parse_key_value_response_no_separator(self):
        result = FastMCPElicitProvider._parse_key_value_response("just-text")
        assert result == {}

    def test_parse_decision_approved_variants(self):
        for val in ["approved", "approve", "yes", "y"]:
            assert FastMCPElicitProvider._parse_decision(val) == ApprovalDecision.APPROVED

    def test_parse_decision_denied_variants(self):
        for val in ["denied", "deny", "no", "n"]:
            assert FastMCPElicitProvider._parse_decision(val) == ApprovalDecision.DENIED

    def test_parse_decision_timeout(self):
        assert FastMCPElicitProvider._parse_decision("timeout") == ApprovalDecision.TIMEOUT

    def test_parse_decision_error(self):
        assert FastMCPElicitProvider._parse_decision("error") == ApprovalDecision.ERROR

    def test_parse_decision_none(self):
        assert FastMCPElicitProvider._parse_decision(None) is None

    def test_parse_decision_unknown(self):
        assert FastMCPElicitProvider._parse_decision("maybe") is None

    def test_parse_scopes_none(self):
        assert FastMCPElicitProvider._parse_scopes(None) == []

    def test_parse_scopes_list(self):
        assert FastMCPElicitProvider._parse_scopes(["read", "write"]) == ["read", "write"]

    def test_parse_scopes_list_with_empty(self):
        assert FastMCPElicitProvider._parse_scopes(["read", "", "write"]) == ["read", "write"]

    def test_parse_scopes_string_csv(self):
        assert FastMCPElicitProvider._parse_scopes("read, write") == ["read", "write"]

    def test_parse_scopes_json_array_string(self):
        assert FastMCPElicitProvider._parse_scopes('["read", "write"]') == ["read", "write"]

    def test_parse_scopes_invalid_json_array(self):
        result = FastMCPElicitProvider._parse_scopes("[broken")
        assert result == ["[broken"]

    def test_parse_scopes_empty_string(self):
        assert FastMCPElicitProvider._parse_scopes("") == []

    def test_parse_scopes_single_value(self):
        assert FastMCPElicitProvider._parse_scopes(42) == ["42"]

    def test_parse_scopes_empty_single_value(self):
        assert FastMCPElicitProvider._parse_scopes("   ") == []

    def test_parse_lease_seconds_none(self):
        assert FastMCPElicitProvider._parse_lease_seconds(None) == 0

    def test_parse_lease_seconds_int(self):
        assert FastMCPElicitProvider._parse_lease_seconds(300) == 300

    def test_parse_lease_seconds_float_string(self):
        assert FastMCPElicitProvider._parse_lease_seconds("300.5") == 300

    def test_parse_lease_seconds_negative(self):
        assert FastMCPElicitProvider._parse_lease_seconds(-10) == 0

    def test_parse_lease_seconds_invalid(self):
        assert FastMCPElicitProvider._parse_lease_seconds("abc") == 0

    def test_parse_approval_payload_with_data_attr(self):
        request = ApprovalRequest(
            request_id="r1",
            tool_name="write_file",
            message="test",
            required_scopes=["write"],
        )
        payload = MagicMock()
        payload.data = json.dumps({
            "decision": "approved",
            "selected_scopes": ["write"],
            "lease_seconds": 300,
        })
        resp = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert resp.decision == ApprovalDecision.APPROVED

    def test_parse_approval_payload_dict(self):
        request = ApprovalRequest(
            request_id="r1",
            tool_name="write_file",
            message="test",
            required_scopes=["write"],
        )
        payload = {
            "decision": "approved",
            "selected_scopes": ["write"],
            "lease_seconds": 300,
        }
        resp = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert resp.decision == ApprovalDecision.APPROVED

    def test_parse_approval_payload_invalid(self):
        request = ApprovalRequest(
            request_id="r1",
            tool_name="write_file",
            message="test",
            required_scopes=["write"],
        )
        resp = FastMCPElicitProvider._parse_approval_payload(request, None)
        assert resp.error_message == "Invalid approval response format"

    def test_parse_approval_payload_no_decision_with_scopes(self):
        request = ApprovalRequest(
            request_id="r1",
            tool_name="write_file",
            message="test",
            required_scopes=["write"],
        )
        payload = {"selected_scopes": ["write"]}
        resp = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert resp.decision == ApprovalDecision.APPROVED

    def test_parse_approval_payload_no_decision_no_scopes(self):
        request = ApprovalRequest(
            request_id="r1",
            tool_name="write_file",
            message="test",
            required_scopes=["write"],
        )
        payload = {"lease_seconds": 300}
        resp = FastMCPElicitProvider._parse_approval_payload(request, payload)
        assert resp.decision == ApprovalDecision.DENIED


# ============================================================================
# SystemdFallbackProvider tests
# ============================================================================


class TestSystemdFallbackProvider:
    @pytest.mark.asyncio
    async def test_is_available_no_binary(self):
        provider = SystemdFallbackProvider()
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 1
            mock_exec.return_value = proc
            result = await provider.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_available_binary_exists(self):
        provider = SystemdFallbackProvider()
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"/usr/bin/systemd-ask-password", b""))
            proc.returncode = 0
            mock_exec.return_value = proc
            result = await provider.is_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_is_available_exception(self):
        provider = SystemdFallbackProvider()
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no exec")):
            result = await provider.is_available()
            assert result is False

    def test_get_name(self):
        provider = SystemdFallbackProvider()
        assert provider.get_name() == "systemd Fallback"

    @pytest.mark.asyncio
    async def test_request_approval_yes(self):
        provider = SystemdFallbackProvider()
        request = ApprovalRequest(
            request_id="req-1",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"yes\n", b""))
            mock_exec.return_value = proc
            resp = await provider.request_approval(request)
            assert resp.decision == ApprovalDecision.APPROVED
            assert resp.selected_scopes == ["write"]

    @pytest.mark.asyncio
    async def test_request_approval_no(self):
        provider = SystemdFallbackProvider()
        request = ApprovalRequest(
            request_id="req-2",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"no\n", b""))
            mock_exec.return_value = proc
            resp = await provider.request_approval(request)
            assert resp.decision == ApprovalDecision.DENIED

    @pytest.mark.asyncio
    async def test_request_approval_exception(self):
        provider = SystemdFallbackProvider()
        request = ApprovalRequest(
            request_id="req-3",
            tool_name="write_file",
            message="Write a file",
            required_scopes=["write"],
        )
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no exec")):
            resp = await provider.request_approval(request)
            assert resp.decision == ApprovalDecision.ERROR


# ============================================================================
# ApprovalProviderFactory tests
# ============================================================================


class TestApprovalProviderFactory:
    @pytest.mark.asyncio
    async def test_create_provider_auto_fastmcp(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        provider = await ApprovalProviderFactory.create_provider(
            provider_name="auto", context=ctx
        )
        assert isinstance(provider, FastMCPElicitProvider)

    @pytest.mark.asyncio
    async def test_create_provider_explicit_fastmcp(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        provider = await ApprovalProviderFactory.create_provider(
            provider_name="fastmcp_elicit", context=ctx
        )
        assert isinstance(provider, FastMCPElicitProvider)

    @pytest.mark.asyncio
    async def test_create_provider_explicit_unavailable_falls_back(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        # Request dbus_gui which is unavailable, should fall back to fastmcp
        provider = await ApprovalProviderFactory.create_provider(
            provider_name="dbus_gui", context=ctx
        )
        assert isinstance(provider, FastMCPElicitProvider)

    @pytest.mark.asyncio
    async def test_create_provider_no_providers_raises(self):
        with patch.object(
            SystemdFallbackProvider, "is_available", new_callable=AsyncMock, return_value=False
        ), patch.object(
            DBusGUIProvider, "is_available", new_callable=AsyncMock, return_value=False
        ):
            with pytest.raises(RuntimeError, match="No approval providers available"):
                await ApprovalProviderFactory.create_provider(
                    provider_name="auto", context=None
                )

    @pytest.mark.asyncio
    async def test_create_provider_env_var(self, monkeypatch):
        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        monkeypatch.setenv("APPROVAL_PROVIDER", "fastmcp_elicit")
        provider = await ApprovalProviderFactory.create_provider(context=ctx)
        assert isinstance(provider, FastMCPElicitProvider)

    @pytest.mark.asyncio
    async def test_create_provider_unknown_explicit_name(self):
        ctx = MagicMock()
        ctx.elicit = AsyncMock()
        # Unknown name defaults to auto
        provider = await ApprovalProviderFactory.create_provider(
            provider_name="unknown_provider", context=ctx
        )
        assert isinstance(provider, FastMCPElicitProvider)


# ============================================================================
# get_approval_provider tests
# ============================================================================


class TestGetApprovalProvider:
    @pytest.mark.asyncio
    async def test_get_approval_provider_creates_singleton(self):
        import src.meta_mcp.governance.approval as approval_module

        original = approval_module._approval_provider
        approval_module._approval_provider = None
        try:
            ctx = MagicMock()
            ctx.elicit = AsyncMock()
            provider = await get_approval_provider(context=ctx)
            assert isinstance(provider, FastMCPElicitProvider)
        finally:
            approval_module._approval_provider = original

    @pytest.mark.asyncio
    async def test_get_approval_provider_returns_cached(self):
        import src.meta_mcp.governance.approval as approval_module

        original = approval_module._approval_provider
        try:
            mock_provider = MagicMock()
            approval_module._approval_provider = mock_provider
            result = await get_approval_provider()
            assert result is mock_provider
        finally:
            approval_module._approval_provider = original

    @pytest.mark.asyncio
    async def test_get_approval_provider_updates_context(self):
        import src.meta_mcp.governance.approval as approval_module

        original = approval_module._approval_provider

        try:
            ctx1 = MagicMock()
            ctx1.elicit = AsyncMock()
            approval_module._approval_provider = None
            provider = await get_approval_provider(context=ctx1)

            ctx2 = MagicMock()
            ctx2.elicit = AsyncMock()
            result = await get_approval_provider(context=ctx2)
            assert result._context is ctx2
        finally:
            approval_module._approval_provider = original
