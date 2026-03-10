"""Tests for validation module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.meta_mcp.validation import (
    run_all_validations,
    validate_bootstrap_tools,
    validate_no_auto_mounts,
)


class TestValidateBootstrapTools:
    """Tests for validate_bootstrap_tools function."""

    @pytest.mark.asyncio
    async def test_validation_passes_when_tools_match(self):
        """Should pass when exposed tools match expected bootstrap tools."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        # Setup expected bootstrap tools
        tool_registry.get_bootstrap_tools.return_value = ["search_tools", "get_tool_schema"]

        # Setup actual exposed tools
        mock_tool_1 = MagicMock()
        mock_tool_1.name = "search_tools"
        mock_tool_2 = MagicMock()
        mock_tool_2.name = "get_tool_schema"

        mcp_instance.get_tools = AsyncMock(return_value={
            "search_tools": mock_tool_1,
            "get_tool_schema": mock_tool_2,
        })

        result = await validate_bootstrap_tools(mcp_instance, tool_registry)

        assert result is True

    @pytest.mark.asyncio
    async def test_validation_fails_with_extra_tools(self):
        """Should fail when extra tools are exposed beyond bootstrap."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        # Expected: only bootstrap tools
        tool_registry.get_bootstrap_tools.return_value = ["search_tools"]

        # Actual: extra tool exposed
        mock_tool_1 = MagicMock()
        mock_tool_1.name = "search_tools"
        mock_tool_2 = MagicMock()
        mock_tool_2.name = "write_file"  # Extra tool!

        mcp_instance.get_tools = AsyncMock(return_value={
            "search_tools": mock_tool_1,
            "write_file": mock_tool_2,
        })

        result = await validate_bootstrap_tools(mcp_instance, tool_registry)

        assert result is False

    @pytest.mark.asyncio
    async def test_validation_fails_with_missing_tools(self):
        """Should fail when bootstrap tools are missing."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        # Expected: two bootstrap tools
        tool_registry.get_bootstrap_tools.return_value = ["search_tools", "get_tool_schema"]

        # Actual: one missing
        mock_tool_1 = MagicMock()
        mock_tool_1.name = "search_tools"

        mcp_instance.get_tools = AsyncMock(return_value={
            "search_tools": mock_tool_1,
        })

        result = await validate_bootstrap_tools(mcp_instance, tool_registry)

        assert result is False

    @pytest.mark.asyncio
    async def test_validation_fails_on_exception(self):
        """Should return False when getting tools raises exception."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        tool_registry.get_bootstrap_tools.return_value = ["search_tools"]
        mcp_instance.get_tools = AsyncMock(side_effect=RuntimeError("Connection failed"))

        result = await validate_bootstrap_tools(mcp_instance, tool_registry)

        assert result is False

    @pytest.mark.asyncio
    async def test_validation_with_empty_bootstrap(self):
        """Should pass when both expected and actual are empty."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        tool_registry.get_bootstrap_tools.return_value = []
        mcp_instance.get_tools = AsyncMock(return_value={})

        result = await validate_bootstrap_tools(mcp_instance, tool_registry)

        assert result is True


class TestValidateNoAutoMounts:
    """Tests for validate_no_auto_mounts function."""

    @pytest.mark.asyncio
    async def test_always_returns_true_placeholder(self):
        """Should always return True (placeholder implementation)."""
        mcp_instance = MagicMock()

        result = await validate_no_auto_mounts(mcp_instance)

        assert result is True

    @pytest.mark.asyncio
    async def test_accepts_any_mcp_instance(self):
        """Should accept any MCP instance."""
        mcp_instance = MagicMock()
        mcp_instance.some_attribute = "value"

        result = await validate_no_auto_mounts(mcp_instance)

        assert result is True


class TestRunAllValidations:
    """Tests for run_all_validations function."""

    @pytest.mark.asyncio
    async def test_runs_all_validations(self):
        """Should run all validation checks."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        # Setup for passing validation
        tool_registry.get_bootstrap_tools.return_value = ["tool1"]
        mock_tool = MagicMock()
        mock_tool.name = "tool1"
        mcp_instance.get_tools = AsyncMock(return_value={"tool1": mock_tool})

        results = await run_all_validations(mcp_instance, tool_registry)

        assert "bootstrap_tools" in results
        assert "no_auto_mounts" in results
        assert results["bootstrap_tools"] is True
        assert results["no_auto_mounts"] is True

    @pytest.mark.asyncio
    async def test_returns_partial_failures(self):
        """Should return results with partial failures."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        # Setup for failing bootstrap validation
        tool_registry.get_bootstrap_tools.return_value = ["expected_tool"]
        mock_tool = MagicMock()
        mock_tool.name = "different_tool"
        mcp_instance.get_tools = AsyncMock(return_value={"different_tool": mock_tool})

        results = await run_all_validations(mcp_instance, tool_registry)

        assert results["bootstrap_tools"] is False
        assert results["no_auto_mounts"] is True  # Always passes

    @pytest.mark.asyncio
    async def test_returns_dict_with_all_checks(self):
        """Should return dict with all validation check names."""
        mcp_instance = MagicMock()
        tool_registry = MagicMock()

        tool_registry.get_bootstrap_tools.return_value = []
        mcp_instance.get_tools = AsyncMock(return_value={})

        results = await run_all_validations(mcp_instance, tool_registry)

        assert isinstance(results, dict)
        assert len(results) == 2
