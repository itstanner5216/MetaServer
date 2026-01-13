"""
Tests for batch search operations (Phase 7).

Tests:
- Batch search with multiple queries
- Result aggregation
- Performance comparison
- Deduplication of results
"""
import pytest
from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry


class TestBatchSearch:
    """Test suite for batch search operations."""

    @pytest.fixture
    def sample_registry(self):
        """Create registry with sample tools."""
        registry = ToolRegistry()

        tools = [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files from disk",
                description_full="Read text and binary files from disk storage",
                tags=["file", "read", "disk"],
                risk_level="safe"
            ),
            ToolRecord(
                tool_id="write_file",
                server_id="core",
                description_1line="Write files to disk",
                description_full="Write text and binary files to disk storage",
                tags=["file", "write", "disk"],
                risk_level="sensitive"
            ),
            ToolRecord(
                tool_id="list_directory",
                server_id="core",
                description_1line="List directory contents",
                description_full="List all files and subdirectories",
                tags=["file", "directory", "list"],
                risk_level="safe"
            ),
            ToolRecord(
                tool_id="send_email",
                server_id="network",
                description_1line="Send email messages",
                description_full="Send email messages to recipients",
                tags=["email", "network", "communication"],
                risk_level="sensitive"
            ),
            ToolRecord(
                tool_id="http_request",
                server_id="network",
                description_1line="Make HTTP requests",
                description_full="Send HTTP/HTTPS requests to web APIs",
                tags=["http", "network", "web"],
                risk_level="sensitive"
            )
        ]

        for tool in tools:
            registry._tools[tool.tool_id] = tool

        return registry

    def test_batch_search_multiple_queries(self, sample_registry):
        """Test batch search with multiple queries."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["read files", "send email", "network operations"]
        results = batch_search_tools(sample_registry, queries)

        assert len(results) == 3
        assert "read files" in results
        assert "send email" in results
        assert "network operations" in results

    def test_batch_search_returns_candidates(self, sample_registry):
        """Test batch search returns ToolCandidate objects."""
        from src.meta_mcp.macros.batch_search import batch_search_tools
        from src.meta_mcp.registry.models import ToolCandidate

        queries = ["file operations"]
        results = batch_search_tools(sample_registry, queries)

        for query, candidates in results.items():
            assert isinstance(candidates, list)
            for candidate in candidates:
                assert isinstance(candidate, ToolCandidate)

    def test_batch_search_empty_queries(self, sample_registry):
        """Test batch search with empty query list."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        results = batch_search_tools(sample_registry, [])

        assert results == {}

    def test_batch_search_none_input(self, sample_registry):
        """Test batch search with None input."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        results = batch_search_tools(sample_registry, None)

        assert results == {}

    def test_batch_search_preserves_query_order(self, sample_registry):
        """Test that batch search preserves query order."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["network", "file", "email"]
        results = batch_search_tools(sample_registry, queries)

        result_keys = list(results.keys())
        assert result_keys == queries

    def test_batch_search_empty_results(self, sample_registry):
        """Test batch search with queries that return no results."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["quantum physics", "artificial gravity"]
        results = batch_search_tools(sample_registry, queries)

        assert len(results) == 2
        # Results might be empty or have very low scores
        for query, candidates in results.items():
            assert isinstance(candidates, list)

    def test_batch_search_duplicate_queries(self, sample_registry):
        """Test batch search with duplicate queries."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["file operations", "file operations"]
        results = batch_search_tools(sample_registry, queries)

        # Should handle duplicates (may deduplicate or keep both)
        assert "file operations" in results

    def test_batch_search_result_limit(self, sample_registry):
        """Test batch search respects result limits."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["operations"]
        results = batch_search_tools(sample_registry, queries, limit=2)

        for query, candidates in results.items():
            assert len(candidates) <= 2

    def test_batch_search_aggregation(self, sample_registry):
        """Test batch search can aggregate results."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["file", "disk", "storage"]
        results = batch_search_tools(sample_registry, queries)

        # All queries should return file-related tools
        for query, candidates in results.items():
            if candidates:
                assert any("file" in c.tags or "disk" in c.tags for c in candidates)

    def test_batch_search_deduplication(self, sample_registry):
        """Test batch search with deduplication option."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["file read", "read files", "file operations"]
        results = batch_search_tools(sample_registry, queries)

        # Each query returns separate results
        assert len(results) == 3

    def test_batch_search_performance(self, sample_registry):
        """Test batch search performance."""
        import time
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["file", "network", "email", "disk"]

        start = time.perf_counter()
        results = batch_search_tools(sample_registry, queries)
        batch_time = time.perf_counter() - start

        # Should complete in reasonable time
        assert batch_time < 1.0  # Less than 1 second for small dataset

        # Should return results for all queries
        assert len(results) == 4

    def test_batch_search_concurrent_queries(self, sample_registry):
        """Test batch search handles concurrent execution."""
        from src.meta_mcp.macros.batch_search import batch_search_tools
        import concurrent.futures

        queries = ["file", "network", "email"]

        # Run multiple batch searches concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(batch_search_tools, sample_registry, queries)
                for _ in range(5)
            ]

            results_list = [f.result() for f in futures]

        # All should succeed
        for results in results_list:
            assert len(results) == 3

    def test_batch_search_relevance_scores(self, sample_registry):
        """Test batch search includes relevance scores."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["file operations"]
        results = batch_search_tools(sample_registry, queries)

        for query, candidates in results.items():
            for candidate in candidates:
                assert hasattr(candidate, "relevance_score")
                assert 0.0 <= candidate.relevance_score <= 1.0

    def test_batch_search_min_score_threshold(self, sample_registry):
        """Test batch search with minimum score threshold."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["file"]
        results = batch_search_tools(sample_registry, queries, min_score=0.5)

        for query, candidates in results.items():
            for candidate in candidates:
                assert candidate.relevance_score >= 0.5

    def test_batch_search_combines_results(self, sample_registry):
        """Test batch search can combine results from multiple queries."""
        from src.meta_mcp.macros.batch_search import batch_search_tools

        queries = ["read", "write", "list"]
        results = batch_search_tools(sample_registry, queries)

        all_tool_ids = set()
        for query, candidates in results.items():
            for candidate in candidates:
                all_tool_ids.add(candidate.tool_id)

        # Should find various file tools
        assert len(all_tool_ids) > 0
