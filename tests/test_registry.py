"""Tests for tool registry."""
import pytest
from src.meta_mcp.registry import tool_registry
from src.meta_mcp.registry.models import ToolCandidate, ToolRecord


def test_registry_loads_from_yaml():
    """Registry should load tools from YAML (Phase 1)."""
    assert tool_registry.is_registered("search_tools")
    assert tool_registry.is_registered("read_file")
    assert tool_registry.is_registered("write_file")
    assert tool_registry.is_registered("git_commit")
    assert tool_registry.is_registered("set_governance_mode")


def test_bootstrap_tools_defined():
    """Bootstrap tools must be exactly search_tools and get_tool_schema (Nuance 5.3)."""
    bootstrap = tool_registry.get_bootstrap_tools()
    assert bootstrap == {"search_tools", "get_tool_schema"}


def test_tool_record_validation():
    """ToolRecord must validate invariants (Nuance 5.1)."""
    tool = tool_registry.get("read_file")
    assert tool is not None
    assert tool.validate_invariants()
    assert tool.risk_level in ["safe", "sensitive", "dangerous"]


def test_search_returns_candidates_not_schemas():
    """Search must return ToolCandidate (no schema field) (Nuance 5.1)."""
    results = tool_registry.search("read file")
    assert len(results) > 0

    # ToolCandidate does NOT have schema fields
    for result in results:
        assert isinstance(result, ToolCandidate)
        assert not hasattr(result, "schema_min")
        assert not hasattr(result, "schema_full")
        assert hasattr(result, "tool_id")
        assert hasattr(result, "description_1line")


def test_search_basic_keyword_matching():
    """Search should find tools by keyword in description or tags."""
    # Search by tool name
    results = tool_registry.search("file")
    tool_ids = [r.tool_id for r in results]
    assert any("file" in tid for tid in tool_ids)

    # Search by operation
    results = tool_registry.search("write")
    assert any("write" in r.tool_id for r in results)


def test_search_returns_limited_results():
    """Search should return at most 8 results."""
    results = tool_registry.search("tool")
    assert len(results) <= 8


def test_search_empty_query():
    """Search with empty query should return empty list."""
    assert tool_registry.search("") == []
    assert tool_registry.search("   ") == []


def test_get_tool_by_id():
    """get() should return ToolRecord for registered tools."""
    tool = tool_registry.get("read_file")
    assert isinstance(tool, ToolRecord)
    assert tool.tool_id == "read_file"
    assert tool.risk_level == "safe"


def test_get_tool_not_found():
    """get() should return None for unregistered tools."""
    tool = tool_registry.get("nonexistent_tool")
    assert tool is None


def test_all_tools_have_required_fields():
    """All tools should have required metadata fields."""
    summaries = tool_registry.get_all_summaries()
    assert len(summaries) == 15  # Total tools from YAML

    for tool in summaries:
        assert tool.tool_id
        assert tool.server_id
        assert tool.description_1line
        assert tool.description_full
        assert tool.tags
        assert tool.risk_level in ["safe", "sensitive", "dangerous"]
        assert isinstance(tool.requires_permission, bool)


def test_bootstrap_tools_are_safe():
    """Bootstrap tools should have risk_level=safe (Nuance 5.3)."""
    search_tool = tool_registry.get("search_tools")
    schema_tool = tool_registry.get("get_tool_schema")

    assert search_tool.risk_level == "safe"
    assert schema_tool.risk_level == "safe"


def test_sensitive_tools_require_permission():
    """Sensitive/dangerous tools should require permission."""
    write_tool = tool_registry.get("write_file")
    delete_tool = tool_registry.get("delete_file")

    assert write_tool.requires_permission is True
    assert delete_tool.requires_permission is True


def test_safe_tools_no_permission():
    """Safe tools should not require permission."""
    read_tool = tool_registry.get("read_file")
    list_tool = tool_registry.get("list_directory")

    assert read_tool.requires_permission is False
    assert list_tool.requires_permission is False


def test_is_registered_works():
    """is_registered() should correctly identify registered tools."""
    assert tool_registry.is_registered("read_file") is True
    assert tool_registry.is_registered("nonexistent") is False
