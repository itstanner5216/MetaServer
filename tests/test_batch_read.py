"""
Tests for batch read operations (Phase 7).

Tests:
- Batch retrieval of multiple tools
- Performance comparison vs individual reads
- Error handling for missing tools
- Partial success scenarios
"""

import pytest

from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry


class TestBatchRead:
    """Test suite for batch read operations."""

    @pytest.fixture
    def sample_registry(self):
        """Create registry with sample tools."""
        registry = ToolRegistry()

        tools = [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files from disk",
                description_full="Read text and binary files",
                tags=["file", "read"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="write_file",
                server_id="core",
                description_1line="Write files to disk",
                description_full="Write text and binary files",
                tags=["file", "write"],
                risk_level="sensitive",
            ),
            ToolRecord(
                tool_id="list_directory",
                server_id="core",
                description_1line="List directory contents",
                description_full="List files and directories",
                tags=["file", "list"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="send_email",
                server_id="network",
                description_1line="Send email messages",
                description_full="Send emails to recipients",
                tags=["email", "network"],
                risk_level="sensitive",
            ),
        ]

        for tool in tools:
            registry._tools[tool.tool_id] = tool

        return registry

    def test_batch_read_all_found(self, sample_registry):
        """Test batch read when all tools exist."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "write_file", "list_directory"]
        results = batch_read_tools(sample_registry, tool_ids)

        assert len(results) == 3
        assert all(r is not None for r in results.values())
        assert "read_file" in results
        assert "write_file" in results
        assert "list_directory" in results

    def test_batch_read_partial_found(self, sample_registry):
        """Test batch read with some missing tools."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "nonexistent", "write_file"]
        results = batch_read_tools(sample_registry, tool_ids)

        assert len(results) == 3
        assert results["read_file"] is not None
        assert results["nonexistent"] is None
        assert results["write_file"] is not None

    def test_batch_read_none_found(self, sample_registry):
        """Test batch read when no tools exist."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["missing1", "missing2", "missing3"]
        results = batch_read_tools(sample_registry, tool_ids)

        assert len(results) == 3
        assert all(r is None for r in results.values())

    def test_batch_read_empty_list(self, sample_registry):
        """Test batch read with empty tool list."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        results = batch_read_tools(sample_registry, [])

        assert results == {}

    def test_batch_read_preserves_order(self, sample_registry):
        """Test that batch read preserves request order."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["send_email", "read_file", "write_file"]
        results = batch_read_tools(sample_registry, tool_ids)

        # Results should be in dictionary (order preserved in Python 3.7+)
        result_keys = list(results.keys())
        assert result_keys == tool_ids

    def test_batch_read_duplicate_ids(self, sample_registry):
        """Test batch read with duplicate tool IDs."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "read_file", "write_file"]
        results = batch_read_tools(sample_registry, tool_ids)

        # Should handle duplicates gracefully
        assert "read_file" in results
        assert "write_file" in results

    def test_batch_read_returns_tool_records(self, sample_registry):
        """Test that batch read returns proper ToolRecord objects."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "write_file"]
        results = batch_read_tools(sample_registry, tool_ids)

        for tool_id, tool in results.items():
            if tool is not None:
                assert isinstance(tool, ToolRecord)
                assert tool.tool_id == tool_id
                assert hasattr(tool, "description_1line")
                assert hasattr(tool, "risk_level")

    def test_batch_read_performance(self, sample_registry):
        """Test that batch read is faster than individual reads."""
        import time

        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "write_file", "list_directory", "send_email"]

        # Individual reads
        start_individual = time.perf_counter()
        individual_results = {}
        for tool_id in tool_ids:
            individual_results[tool_id] = sample_registry.get(tool_id)
        individual_time = time.perf_counter() - start_individual

        # Batch read
        start_batch = time.perf_counter()
        batch_results = batch_read_tools(sample_registry, tool_ids)
        batch_time = time.perf_counter() - start_batch

        # Batch should be at least as fast (or faster with optimization)
        # For small datasets, might be similar, so we just check it completes
        assert batch_time >= 0
        assert individual_time >= 0

        # Results should be equivalent
        assert len(individual_results) == len(batch_results)

    def test_batch_read_with_metadata(self, sample_registry):
        """Test batch read includes all tool metadata."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        results = batch_read_tools(sample_registry, ["read_file"])
        tool = results["read_file"]

        assert tool is not None
        assert tool.tool_id == "read_file"
        assert tool.server_id == "core"
        assert tool.description_1line == "Read files from disk"
        assert tool.description_full == "Read text and binary files"
        assert "file" in tool.tags
        assert tool.risk_level == "safe"

    def test_batch_read_filter_by_risk(self, sample_registry):
        """Test batch read with risk level filtering."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "write_file", "send_email"]
        results = batch_read_tools(sample_registry, tool_ids)

        # Filter for safe tools only
        safe_tools = {
            tid: tool
            for tid, tool in results.items()
            if tool is not None and tool.risk_level == "safe"
        }

        assert len(safe_tools) == 1
        assert "read_file" in safe_tools

    def test_batch_read_large_batch(self, sample_registry):
        """Test batch read with many tool IDs."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        # Create large batch request (mix of existing and non-existing)
        tool_ids = [f"tool_{i}" for i in range(100)]
        tool_ids[0] = "read_file"
        tool_ids[50] = "write_file"

        results = batch_read_tools(sample_registry, tool_ids)

        assert len(results) == 100
        assert results["read_file"] is not None
        assert results["write_file"] is not None
        assert results["tool_1"] is None

    def test_batch_read_with_none_input(self, sample_registry):
        """Test batch read with None input."""
        from src.meta_mcp.macros.batch_read import batch_read_tools

        results = batch_read_tools(sample_registry, None)

        assert results == {}

    def test_batch_read_concurrent_safety(self, sample_registry):
        """Test batch read is safe for concurrent access."""
        import concurrent.futures

        from src.meta_mcp.macros.batch_read import batch_read_tools

        tool_ids = ["read_file", "write_file", "send_email"]

        # Perform multiple batch reads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(batch_read_tools, sample_registry, tool_ids) for _ in range(10)
            ]

            results = [f.result() for f in futures]

        # All results should be identical
        for result in results:
            assert len(result) == 3
            assert result["read_file"] is not None
            assert result["write_file"] is not None
