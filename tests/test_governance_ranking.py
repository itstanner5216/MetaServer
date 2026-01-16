"""Tests for governance-aware ranking in semantic search."""

from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry
from src.meta_mcp.retrieval.search import SemanticSearch
from src.meta_mcp.state import ExecutionMode, governance_state


def test_governance_ranking_blocks_sensitive(monkeypatch):
    """Blocked tools should rank below allowed tools in READ_ONLY mode."""

    async def _read_only_mode():
        return ExecutionMode.READ_ONLY

    monkeypatch.setattr(governance_state, "get_mode", _read_only_mode)

    registry = ToolRegistry()
    registry._tools = {
        "safe_tool": ToolRecord(
            tool_id="safe_tool",
            server_id="core",
            description_1line="File tool for read operations",
            description_full="File tool for read operations",
            tags=["file", "read"],
            risk_level="safe",
        ),
        "danger_tool": ToolRecord(
            tool_id="danger_tool",
            server_id="core",
            description_1line="File tool for read operations",
            description_full="File tool for read operations",
            tags=["file", "read"],
            risk_level="dangerous",
        ),
    }

    searcher = SemanticSearch(registry)
    results = searcher.search("file read")

    assert results[0].tool_id == "safe_tool"
    assert results[0].relevance_score >= results[1].relevance_score


def test_governance_ranking_requires_approval(monkeypatch):
    """Approval-required tools should rank below allowed tools in PERMISSION mode."""

    async def _permission_mode():
        return ExecutionMode.PERMISSION

    monkeypatch.setattr(governance_state, "get_mode", _permission_mode)

    registry = ToolRegistry()
    registry._tools = {
        "safe_tool": ToolRecord(
            tool_id="safe_tool",
            server_id="core",
            description_1line="Network tool for HTTP requests",
            description_full="Network tool for HTTP requests",
            tags=["network", "http"],
            risk_level="safe",
        ),
        "sensitive_tool": ToolRecord(
            tool_id="sensitive_tool",
            server_id="core",
            description_1line="Network tool for HTTP requests",
            description_full="Network tool for HTTP requests",
            tags=["network", "http"],
            risk_level="sensitive",
        ),
    }

    searcher = SemanticSearch(registry)
    results = searcher.search("http request")

    assert results[0].tool_id == "safe_tool"
    assert results[0].relevance_score >= results[1].relevance_score
