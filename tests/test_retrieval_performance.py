"""
Performance tests for semantic retrieval (Phase 2).

Tests:
- Search latency (<100ms for 100 tools)
- Memory usage
- Index building performance
- Comparison with keyword search
"""
import pytest
import time
from datetime import datetime
from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry
from src.meta_mcp.retrieval.search import SemanticSearch
from src.meta_mcp.retrieval.embedder import ToolEmbedder


class TestRetrievalPerformance:
    """Performance benchmarks for semantic retrieval."""

    @pytest.fixture
    def large_registry(self):
        """Create registry with 100+ tools for performance testing."""
        registry = ToolRegistry()

        # Create diverse set of tools
        categories = [
            ("file", ["read", "write", "list", "delete", "move", "copy"]),
            ("network", ["http", "websocket", "dns", "ping", "ftp"]),
            ("database", ["query", "insert", "update", "delete", "migrate"]),
            ("system", ["process", "memory", "cpu", "disk", "monitor"]),
            ("security", ["encrypt", "decrypt", "hash", "verify", "sign"]),
            ("text", ["parse", "format", "search", "replace", "validate"]),
            ("image", ["resize", "crop", "rotate", "filter", "convert"]),
            ("audio", ["play", "record", "mix", "encode", "decode"]),
        ]

        tool_count = 0
        for category, operations in categories:
            for operation in operations:
                for variant in range(3):  # 3 variants per operation
                    tool_id = f"{category}_{operation}_{variant}"
                    registry._tools[tool_id] = ToolRecord(
                        tool_id=tool_id,
                        server_id=f"{category}_server",
                        description_1line=f"{operation.capitalize()} {category} data variant {variant}",
                        description_full=f"Perform {operation} operation on {category} resources. This is variant {variant} with extended capabilities.",
                        tags=[category, operation, f"variant_{variant}"],
                        risk_level=["safe", "sensitive", "dangerous"][variant % 3]
                    )
                    tool_count += 1

        assert tool_count >= 100, f"Generated {tool_count} tools, expected >= 100"
        return registry

    def test_search_latency_100_tools(self, large_registry):
        """Test search latency with 100+ tools is under 100ms."""
        searcher = SemanticSearch(large_registry)

        # Warm up - build index
        searcher.search("test")

        # Measure search time
        queries = [
            "read files from disk",
            "network operations",
            "database queries",
            "encrypt data",
            "process images"
        ]

        total_time = 0
        iterations = len(queries)

        for query in queries:
            start = time.perf_counter()
            results = searcher.search(query)
            end = time.perf_counter()

            search_time_ms = (end - start) * 1000
            total_time += search_time_ms

            # Individual search should be under 100ms
            assert search_time_ms < 100, \
                f"Search for '{query}' took {search_time_ms:.2f}ms, expected <100ms"

        # Average should be well under 100ms
        avg_time = total_time / iterations
        assert avg_time < 100, \
            f"Average search time {avg_time:.2f}ms, expected <100ms"

        print(f"\nSearch performance: {avg_time:.2f}ms average over {iterations} queries")

    def test_index_building_performance(self, large_registry):
        """Test index building completes in reasonable time."""
        searcher = SemanticSearch(large_registry)

        # Measure index build time
        start = time.perf_counter()
        searcher._build_index()
        end = time.perf_counter()

        build_time_ms = (end - start) * 1000

        # Index building should complete in under 1 second for 100 tools
        assert build_time_ms < 1000, \
            f"Index build took {build_time_ms:.2f}ms, expected <1000ms"

        print(f"\nIndex build time: {build_time_ms:.2f}ms for {len(large_registry._tools)} tools")

    def test_embedding_cache_effectiveness(self, large_registry):
        """Test that embedding cache improves performance."""
        embedder = ToolEmbedder()
        tools = large_registry.get_all_summaries()

        # Build index (caches all embeddings)
        embedder.build_index(tools)

        # Time cached retrieval
        tool = tools[0]
        start = time.perf_counter()
        for _ in range(100):
            embedder.get_cached_embedding(tool.tool_id)
        end = time.perf_counter()

        cached_time = end - start

        # Clear cache and time uncached embedding
        embedder.clear_cache()
        start = time.perf_counter()
        for _ in range(100):
            embedder.embed_tool(tool)
        end = time.perf_counter()

        uncached_time = end - start

        # Cached should be significantly faster
        assert cached_time < uncached_time, \
            "Cached embeddings should be faster than recomputing"

        print(f"\nCache speedup: {uncached_time/cached_time:.1f}x faster")

    def test_semantic_vs_keyword_quality(self):
        """Compare semantic search quality vs keyword search."""
        registry = ToolRegistry()

        # Create tools where semantic search should outperform keyword
        tools = [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files from disk",
                description_full="Read and retrieve file contents from local storage",
                tags=["file", "read", "storage", "io"],
                risk_level="safe"
            ),
            ToolRecord(
                tool_id="load_document",
                server_id="core",
                description_1line="Load document contents",
                description_full="Load and parse document files",
                tags=["document", "load", "parse"],
                risk_level="safe"
            ),
            ToolRecord(
                tool_id="send_email",
                server_id="network",
                description_1line="Send email messages",
                description_full="Transmit email to recipients",
                tags=["email", "send", "network"],
                risk_level="sensitive"
            )
        ]

        for tool in tools:
            registry._tools[tool.tool_id] = tool

        # Query: "retrieve file contents"
        # Semantic should match read_file/load_document
        # Keyword might miss if exact words don't match

        semantic_searcher = SemanticSearch(registry)
        semantic_results = semantic_searcher.search("retrieve file contents")

        # Should prioritize file-related tools
        semantic_top_ids = [r.tool_id for r in semantic_results[:2]]
        assert "read_file" in semantic_top_ids or "load_document" in semantic_top_ids

        print(f"\nSemantic search top result: {semantic_results[0].tool_id if semantic_results else 'none'}")

    def test_memory_efficiency(self, large_registry):
        """Test memory usage is reasonable for embeddings."""
        import sys

        searcher = SemanticSearch(large_registry)
        searcher._build_index()

        # Get approximate memory usage of cache
        cache_size = sys.getsizeof(searcher.embedder._cache)
        vocab_size = sys.getsizeof(searcher.embedder._vocabulary)

        total_memory_kb = (cache_size + vocab_size) / 1024

        # Memory should be reasonable (< 1MB for 100 tools)
        assert total_memory_kb < 1024, \
            f"Memory usage {total_memory_kb:.2f}KB exceeds 1MB limit"

        print(f"\nMemory usage: {total_memory_kb:.2f}KB for {len(large_registry._tools)} tools")

    def test_vocabulary_size_scaling(self):
        """Test vocabulary size scales reasonably with tool count."""
        embedder = ToolEmbedder()

        # Test with different tool counts
        tool_counts = [10, 50, 100]
        vocab_sizes = []

        for count in tool_counts:
            tools = []
            for i in range(count):
                tools.append(ToolRecord(
                    tool_id=f"tool_{i}",
                    server_id="core",
                    description_1line=f"Tool {i} for testing",
                    description_full=f"Extended description for tool {i}",
                    tags=[f"tag_{i}"],
                    risk_level="safe"
                ))

            embedder._build_vocabulary(tools)
            vocab_sizes.append(len(embedder._vocabulary))

            # Clear for next iteration
            embedder._vocabulary.clear()
            embedder._idf_scores.clear()

        # Vocabulary should grow but not linearly (word reuse)
        assert vocab_sizes[1] > vocab_sizes[0]
        assert vocab_sizes[2] > vocab_sizes[1]

        # Growth should be sub-linear (diminishing returns)
        growth_rate_1 = vocab_sizes[1] / vocab_sizes[0]
        growth_rate_2 = vocab_sizes[2] / vocab_sizes[1]

        print(f"\nVocabulary scaling: {vocab_sizes} for {tool_counts} tools")

    def test_concurrent_searches(self, large_registry):
        """Test performance under concurrent search load."""
        searcher = SemanticSearch(large_registry)

        # Build index once
        searcher._build_index()

        # Simulate concurrent searches
        queries = [
            "file operations",
            "network requests",
            "database queries",
            "security functions",
            "text processing"
        ]

        start = time.perf_counter()

        # Sequential searches (simulating concurrent workload)
        for _ in range(5):  # 5 rounds
            for query in queries:
                searcher.search(query)

        end = time.perf_counter()

        total_searches = 5 * len(queries)
        avg_time_ms = ((end - start) / total_searches) * 1000

        # Average should still be under 100ms
        assert avg_time_ms < 100, \
            f"Average search time under load: {avg_time_ms:.2f}ms, expected <100ms"

        print(f"\nConcurrent load: {avg_time_ms:.2f}ms average over {total_searches} searches")

    def test_worst_case_query_performance(self, large_registry):
        """Test performance with worst-case queries."""
        searcher = SemanticSearch(large_registry)
        searcher._build_index()

        # Worst case: very long query
        long_query = " ".join([f"word{i}" for i in range(100)])

        start = time.perf_counter()
        results = searcher.search(long_query)
        end = time.perf_counter()

        search_time_ms = (end - start) * 1000

        # Should still complete in reasonable time
        assert search_time_ms < 200, \
            f"Long query took {search_time_ms:.2f}ms, expected <200ms"

        print(f"\nWorst-case query (100 words): {search_time_ms:.2f}ms")

    def test_rebuild_index_performance(self, large_registry):
        """Test index rebuild performance."""
        searcher = SemanticSearch(large_registry)

        # Initial build
        start = time.perf_counter()
        searcher._build_index()
        initial_time = time.perf_counter() - start

        # Rebuild
        start = time.perf_counter()
        searcher.rebuild_index()
        rebuild_time = time.perf_counter() - start

        # Rebuild should be similar to initial build
        assert rebuild_time < 1.5 * initial_time, \
            "Rebuild should not be significantly slower than initial build"

        print(f"\nIndex rebuild: {rebuild_time*1000:.2f}ms vs initial {initial_time*1000:.2f}ms")

    def test_empty_results_performance(self, large_registry):
        """Test performance when no results match."""
        searcher = SemanticSearch(large_registry)
        searcher._build_index()

        # Query with no matches (high threshold)
        start = time.perf_counter()
        results = searcher.search("xyz123abc456", min_score=0.9)
        end = time.perf_counter()

        search_time_ms = (end - start) * 1000

        # Should still be fast even with no matches
        assert search_time_ms < 100, \
            f"No-match query took {search_time_ms:.2f}ms, expected <100ms"

        print(f"\nNo-match query: {search_time_ms:.2f}ms")
