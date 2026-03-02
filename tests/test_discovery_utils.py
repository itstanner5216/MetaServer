"""Tests for discovery_utils module."""

import pytest

from src.meta_mcp.discovery_utils import _format_tool_entry, format_search_results
from src.meta_mcp.registry.models import ToolCandidate, ToolRecord


def _make_tool_candidate(tool_id, description, risk_level="safe"):
    """Helper to create ToolCandidate with required fields."""
    return ToolCandidate(
        tool_id=tool_id,
        server_id="test_server",
        description_1line=description,
        tags=["test"],
        risk_level=risk_level,
    )


def _make_tool_record(tool_id, description, risk_level="safe"):
    """Helper to create ToolRecord with required fields."""
    return ToolRecord(
        tool_id=tool_id,
        server_id="test_server",
        description_1line=description,
        description_full=description,
        tags=["test"],
        risk_level=risk_level,
    )


class TestFormatToolEntry:
    """Tests for _format_tool_entry function."""

    def test_format_safe_tool(self):
        """Should format safe tool with [SAFE] flag."""
        tool = _make_tool_candidate("read_file", "Read contents of a file", "safe")
        
        result = _format_tool_entry(tool)
        
        assert len(result) == 3
        assert "• read_file [SAFE]" in result[0]
        assert "Read contents of a file" in result[1]
        assert result[2] == ""

    def test_format_sensitive_tool(self):
        """Should format sensitive tool with [SENSITIVE] flag."""
        tool = _make_tool_candidate("write_file", "Write data to a file", "sensitive")
        
        result = _format_tool_entry(tool)
        
        assert "[SENSITIVE]" in result[0]
        assert "write_file" in result[0]

    def test_format_high_risk_tool(self):
        """Should format high risk tool as SENSITIVE."""
        tool = _make_tool_candidate("delete_file", "Delete a file permanently", "dangerous")
        
        result = _format_tool_entry(tool)
        
        assert "[SENSITIVE]" in result[0]

    def test_format_tool_record(self):
        """Should also work with ToolRecord objects."""
        tool = _make_tool_record("search_tools", "Search for available tools", "safe")
        
        result = _format_tool_entry(tool)
        
        assert "search_tools" in result[0]
        assert "[SAFE]" in result[0]


class TestFormatSearchResults:
    """Tests for format_search_results function."""

    def test_format_empty_results(self):
        """Should return no tools message for empty results."""
        result = format_search_results([])
        
        assert result == "No tools found matching your query."

    def test_format_single_result(self):
        """Should format single result correctly."""
        tools = [_make_tool_candidate("read_file", "Read file contents", "safe")]
        
        result = format_search_results(tools)
        
        assert "Found 1 tool(s):" in result
        assert "read_file" in result
        assert "[SAFE]" in result
        assert "Read file contents" in result

    def test_format_multiple_results(self):
        """Should format multiple results correctly."""
        tools = [
            _make_tool_candidate("read_file", "Read file contents", "safe"),
            _make_tool_candidate("write_file", "Write file contents", "sensitive"),
            _make_tool_candidate("delete_file", "Delete a file", "dangerous"),
        ]
        
        result = format_search_results(tools)
        
        assert "Found 3 tool(s):" in result
        assert "read_file" in result
        assert "write_file" in result
        assert "delete_file" in result

    def test_format_mixed_risk_levels(self):
        """Should correctly format tools with different risk levels."""
        tools = [
            _make_tool_candidate("safe_tool", "A safe operation", "safe"),
            _make_tool_candidate("risky_tool", "A risky operation", "sensitive"),
        ]
        
        result = format_search_results(tools)
        
        assert "[SAFE]" in result
        assert "[SENSITIVE]" in result

    def test_format_iterable_input(self):
        """Should work with any iterable, not just lists."""
        def generate_tools():
            yield _make_tool_candidate("tool1", "First tool", "safe")
            yield _make_tool_candidate("tool2", "Second tool", "safe")
        
        result = format_search_results(generate_tools())
        
        assert "Found 2 tool(s):" in result
        assert "tool1" in result
        assert "tool2" in result

    def test_format_tool_records(self):
        """Should work with ToolRecord objects."""
        tools = [_make_tool_record("search_tools", "Search available tools", "safe")]
        
        result = format_search_results(tools)
        
        assert "Found 1 tool(s):" in result
        assert "search_tools" in result

    def test_result_does_not_contain_schemas(self):
        """Should not include schema details in output."""
        tools = [_make_tool_candidate("complex_tool", "A tool with many features", "safe")]
        
        result = format_search_results(tools)
        
        # Should not contain schema-related terms (other than in tool description)
        assert "arguments" not in result.lower()
        assert "parameters" not in result.lower()
        assert "inputSchema" not in result
