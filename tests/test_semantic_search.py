"""
Tests for semantic search (Phase 2).

Tests:
- Query matching (relevant tools ranked higher)
- Ranking quality (more relevant = higher rank)
- Integration with registry
- Edge cases and error handling
"""
import pytest
from datetime import datetime
from src.meta_mcp.registry.models import ToolRecord, ToolCandidate
from src.meta_mcp.registry.registry import ToolRegistry
from src.meta_mcp.retrieval.search import SemanticSearch, search_tools_semantic
from src.meta_mcp.retrieval.embedder import ToolEmbedder


class TestSemanticSearch:
    """Test suite for SemanticSearch class."""

    @pytest.fixture
    def sample_tools(self):
        """Create sample tools for testing."""
        return [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files from disk",
                description_full="Read text and binary files from the file system",
                tags=["file", "read", "disk", "io"],
                risk_level="safe"
            ),
            ToolRecord(
                tool_id="write_file",
                server_id="core",
                description_1line="Write files to disk",
                description_full="Write text and binary files to the file system",
                tags=["file", "write", "disk", "io"],
                risk_level="sensitive"
            ),
            ToolRecord(
                tool_id="list_directory",
                server_id="core",
                description_1line="List directory contents",
                description_full="List all files and subdirectories in a directory",
                tags=["file", "directory", "list"],
                risk_level="safe"
            ),
            ToolRecord(
                tool_id="send_email",
                server_id="network",
                description_1line="Send email messages",
                description_full="Send email messages to one or more recipients",
                tags=["email", "network", "send", "communication"],
                risk_level="sensitive"
            ),
            ToolRecord(
                tool_id="http_request",
                server_id="network",
                description_1line="Make HTTP requests",
                description_full="Send HTTP/HTTPS requests to web endpoints",
                tags=["http", "network", "web", "api"],
                risk_level="sensitive"
            ),
            ToolRecord(
                tool_id="execute_shell",
                server_id="system",
                description_1line="Execute shell commands",
                description_full="Run shell commands on the system",
                tags=["shell", "system", "execute", "command"],
                risk_level="dangerous"
            )
        ]

    @pytest.fixture
    def registry_with_tools(self, sample_tools):
        """Create registry populated with sample tools."""
        registry = ToolRegistry()
        for tool in sample_tools:
            registry._tools[tool.tool_id] = tool
        return registry

    def test_semantic_search_initialization(self, registry_with_tools):
        """Test semantic search initializes correctly."""
        searcher = SemanticSearch(registry_with_tools)

        assert searcher.registry == registry_with_tools
        assert isinstance(searcher.embedder, ToolEmbedder)
        assert searcher._index_built is False

    def test_lazy_index_building(self, registry_with_tools):
        """Test index is built lazily on first search."""
        searcher = SemanticSearch(registry_with_tools)

        # Index not built initially
        assert searcher._index_built is False

        # Perform search
        results = searcher.search("read files")

        # Index should now be built
        assert searcher._index_built is True

    def test_search_file_operations(self, registry_with_tools):
        """Test search for file-related operations."""
        searcher = SemanticSearch(registry_with_tools)

        # Search for file operations
        results = searcher.search("read files from disk")

        # Should return file-related tools
        assert len(results) > 0
        assert isinstance(results[0], ToolCandidate)

        # read_file should be highly ranked
        tool_ids = [r.tool_id for r in results]
        assert "read_file" in tool_ids[:3]  # Top 3 results

    def test_search_network_operations(self, registry_with_tools):
        """Test search for network-related operations."""
        searcher = SemanticSearch(registry_with_tools)

        # Search for network operations
        results = searcher.search("send HTTP request to web API")

        # Should return network-related tools
        assert len(results) > 0

        # http_request should be highly ranked
        tool_ids = [r.tool_id for r in results]
        assert "http_request" in tool_ids[:3]

    def test_search_ranking_quality(self, registry_with_tools):
        """Test that more relevant tools are ranked higher."""
        searcher = SemanticSearch(registry_with_tools)

        # Search for specific operation
        results = searcher.search("write files to disk")

        # write_file should be ranked higher than send_email
        scores = {r.tool_id: r.relevance_score for r in results}

        if "write_file" in scores and "send_email" in scores:
            assert scores["write_file"] > scores["send_email"]

    def test_relevance_scores(self, registry_with_tools):
        """Test relevance scores are computed correctly."""
        searcher = SemanticSearch(registry_with_tools)

        results = searcher.search("file operations")

        # All results should have relevance scores
        for result in results:
            assert 0.0 <= result.relevance_score <= 1.0

        # Scores should be in descending order
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_limit(self, registry_with_tools):
        """Test result limit parameter."""
        searcher = SemanticSearch(registry_with_tools)

        # Limit to 3 results
        results = searcher.search("operations", limit=3)
        assert len(results) <= 3

        # Limit to 10 results
        results = searcher.search("operations", limit=10)
        assert len(results) <= 10

    def test_minimum_score_threshold(self, registry_with_tools):
        """Test minimum score threshold filtering."""
        searcher = SemanticSearch(registry_with_tools)

        # High threshold should return fewer results
        results_high = searcher.search("files", min_score=0.5)
        results_low = searcher.search("files", min_score=0.1)

        # Lower threshold should have same or more results
        assert len(results_low) >= len(results_high)

        # All results should meet threshold
        for result in results_high:
            assert result.relevance_score >= 0.5

    def test_empty_query(self, registry_with_tools):
        """Test empty query returns no results."""
        searcher = SemanticSearch(registry_with_tools)

        assert searcher.search("") == []
        assert searcher.search("   ") == []
        assert searcher.search(None) == []

    def test_no_matching_results(self, registry_with_tools):
        """Test query with no relevant matches."""
        searcher = SemanticSearch(registry_with_tools)

        # Query completely unrelated to tools
        results = searcher.search("quantum physics calculations", min_score=0.3)

        # Should return empty or very few results
        assert len(results) <= 1

    def test_cosine_similarity_calculation(self, registry_with_tools):
        """Test cosine similarity computation."""
        searcher = SemanticSearch(registry_with_tools)

        # Identical vectors
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        assert searcher._cosine_similarity(vec1, vec2) == 1.0

        # Orthogonal vectors
        vec3 = [1.0, 0.0, 0.0]
        vec4 = [0.0, 1.0, 0.0]
        assert searcher._cosine_similarity(vec3, vec4) == 0.0

        # Empty vectors
        assert searcher._cosine_similarity([], []) == 0.0

        # Mismatched lengths
        assert searcher._cosine_similarity([1.0], [1.0, 0.0]) == 0.0

    def test_tool_candidate_structure(self, registry_with_tools):
        """Test that results are proper ToolCandidate objects."""
        searcher = SemanticSearch(registry_with_tools)

        results = searcher.search("file operations")

        for result in results:
            assert isinstance(result, ToolCandidate)
            assert hasattr(result, "tool_id")
            assert hasattr(result, "server_id")
            assert hasattr(result, "description_1line")
            assert hasattr(result, "tags")
            assert hasattr(result, "risk_level")
            assert hasattr(result, "relevance_score")

            # Should NOT have schema fields
            assert not hasattr(result, "schema_min")
            assert not hasattr(result, "schema_full")

    def test_rebuild_index(self, registry_with_tools):
        """Test index rebuilding."""
        searcher = SemanticSearch(registry_with_tools)

        # Initial search builds index
        results1 = searcher.search("files")
        assert searcher._index_built is True

        # Rebuild index
        searcher.rebuild_index()

        # Should still be built
        assert searcher._index_built is True

        # Search should still work
        results2 = searcher.search("files")
        assert len(results2) > 0

    def test_convenience_function(self, registry_with_tools):
        """Test convenience search function."""
        results = search_tools_semantic(registry_with_tools, "file operations")

        assert len(results) > 0
        assert all(isinstance(r, ToolCandidate) for r in results)

    def test_multi_word_queries(self, registry_with_tools):
        """Test queries with multiple words."""
        searcher = SemanticSearch(registry_with_tools)

        # Multi-word query
        results = searcher.search("read write files disk")

        # Should prioritize file operations
        tool_ids = [r.tool_id for r in results[:3]]
        assert any(tid in tool_ids for tid in ["read_file", "write_file"])

    def test_tag_matching(self, registry_with_tools):
        """Test that tags contribute to relevance."""
        searcher = SemanticSearch(registry_with_tools)

        # Query matching tags
        results = searcher.search("email communication")

        # send_email should be ranked high (has both tags)
        if len(results) > 0:
            top_ids = [r.tool_id for r in results[:3]]
            assert "send_email" in top_ids

    def test_description_matching(self, registry_with_tools):
        """Test matching against full descriptions."""
        searcher = SemanticSearch(registry_with_tools)

        # Query matching full description
        results = searcher.search("list subdirectories")

        # list_directory should rank high
        if len(results) > 0:
            top_ids = [r.tool_id for r in results[:2]]
            assert "list_directory" in top_ids

    def test_risk_level_preserved(self, registry_with_tools):
        """Test that risk levels are preserved in results."""
        searcher = SemanticSearch(registry_with_tools)

        results = searcher.search("operations")

        # Check risk levels are preserved
        for result in results:
            assert result.risk_level in ["safe", "sensitive", "dangerous"]

    def test_server_id_preserved(self, registry_with_tools):
        """Test that server IDs are preserved in results."""
        searcher = SemanticSearch(registry_with_tools)

        results = searcher.search("operations")

        # Check server IDs are preserved
        for result in results:
            assert result.server_id in ["core", "network", "system"]

    def test_search_with_special_characters(self, registry_with_tools):
        """Test queries with special characters."""
        searcher = SemanticSearch(registry_with_tools)

        # Query with special chars
        results = searcher.search("HTTP/HTTPS requests!")

        # Should still work and find http_request
        tool_ids = [r.tool_id for r in results]
        assert "http_request" in tool_ids

    def test_empty_registry(self):
        """Test search on empty registry."""
        registry = ToolRegistry()
        searcher = SemanticSearch(registry)

        results = searcher.search("anything")

        assert results == []

    def test_single_tool_registry(self):
        """Test search with single tool."""
        registry = ToolRegistry()
        registry._tools["only_tool"] = ToolRecord(
            tool_id="only_tool",
            server_id="core",
            description_1line="Only tool",
            description_full="The only tool available",
            tags=["only"],
            risk_level="safe"
        )

        searcher = SemanticSearch(registry)
        results = searcher.search("tool")

        assert len(results) == 1
        assert results[0].tool_id == "only_tool"

    def test_search_persistence(self, registry_with_tools):
        """Test that multiple searches work correctly."""
        searcher = SemanticSearch(registry_with_tools)

        # Multiple searches should all work
        results1 = searcher.search("files")
        results2 = searcher.search("network")
        results3 = searcher.search("system")

        assert len(results1) > 0
        assert len(results2) > 0
        assert len(results3) > 0

        # Different queries should have different top results
        assert results1[0].tool_id != results2[0].tool_id or \
               results1[0].tool_id != results3[0].tool_id
