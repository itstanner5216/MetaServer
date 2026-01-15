"""
Tests for tool embedder (Phase 2).

Tests:
- Embedding consistency (same input → same output)
- Embedding similarity (related tools have similar embeddings)
- Cache functionality
- Edge cases (empty descriptions, special characters)
"""

from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.retrieval.embedder import ToolEmbedder


class TestToolEmbedder:
    """Test suite for ToolEmbedder class."""

    def test_embedder_initialization(self):
        """Test embedder initializes with empty state."""
        embedder = ToolEmbedder()
        assert embedder._cache == {}
        assert embedder._vocabulary == set()
        assert embedder._idf_scores == {}
        assert embedder._document_count == 0

    def test_tokenize_basic(self):
        """Test basic tokenization."""
        embedder = ToolEmbedder()

        # Simple text
        tokens = embedder._tokenize("read file from disk")
        assert tokens == ["read", "file", "from", "disk"]

        # With punctuation
        tokens = embedder._tokenize("read_file, write_file!")
        assert "read_file" in tokens
        assert "write_file" in tokens

        # Mixed case
        tokens = embedder._tokenize("READ File WRITE")
        assert all(t.islower() for t in tokens)

    def test_tokenize_special_characters(self):
        """Test tokenization with special characters."""
        embedder = ToolEmbedder()

        # Underscores preserved
        tokens = embedder._tokenize("read_file_system")
        assert "read_file_system" in tokens

        # Numbers preserved
        tokens = embedder._tokenize("tool123 version2")
        assert "tool123" in tokens
        assert "version2" in tokens

        # Special chars removed
        tokens = embedder._tokenize("hello@world.com#test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "com" in tokens
        assert "test" in tokens

    def test_build_vocabulary(self):
        """Test vocabulary building from tools."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files",
                description_full="Read files from disk",
                tags=["file", "read"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="write_file",
                server_id="core",
                description_1line="Write files",
                description_full="Write files to disk",
                tags=["file", "write"],
                risk_level="sensitive",
            ),
        ]

        embedder._build_vocabulary(tools)

        # Check vocabulary contains expected words
        assert "read" in embedder._vocabulary
        assert "write" in embedder._vocabulary
        assert "file" in embedder._vocabulary
        assert "files" in embedder._vocabulary
        assert "disk" in embedder._vocabulary

        # Check IDF scores exist
        assert "file" in embedder._idf_scores
        assert embedder._idf_scores["file"] > 0

        # Document count should match
        assert embedder._document_count == 2

    def test_embedding_consistency(self):
        """Test that same input produces same embedding."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="test_tool",
                server_id="core",
                description_1line="Test tool",
                description_full="A test tool for testing",
                tags=["test"],
                risk_level="safe",
            )
        ]

        embedder.build_index(tools)

        # Embed same tool multiple times
        embedding1 = embedder.embed_tool(tools[0])
        embedding2 = embedder.embed_tool(tools[0])

        assert embedding1 == embedding2
        assert len(embedding1) > 0

    def test_embedding_normalization(self):
        """Test that embeddings are normalized to unit length."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="test_tool",
                server_id="core",
                description_1line="Test tool with long description",
                description_full="A very long test tool for testing normalization",
                tags=["test", "long", "description"],
                risk_level="safe",
            )
        ]

        embedder.build_index(tools)
        embedding = embedder.embed_tool(tools[0])

        # Calculate magnitude
        magnitude = sum(x * x for x in embedding) ** 0.5

        # Should be approximately 1.0 (allowing for floating point errors)
        assert abs(magnitude - 1.0) < 1e-6

    def test_embedding_similarity(self):
        """Test that similar tools have similar embeddings."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files from disk",
                description_full="Read files from disk storage",
                tags=["file", "read", "disk"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="write_file",
                server_id="core",
                description_1line="Write files to disk",
                description_full="Write files to disk storage",
                tags=["file", "write", "disk"],
                risk_level="sensitive",
            ),
            ToolRecord(
                tool_id="send_email",
                server_id="network",
                description_1line="Send email messages",
                description_full="Send email messages to recipients",
                tags=["email", "network", "send"],
                risk_level="sensitive",
            ),
        ]

        embedder.build_index(tools)

        emb_read = embedder.embed_tool(tools[0])
        emb_write = embedder.embed_tool(tools[1])
        emb_email = embedder.embed_tool(tools[2])

        # Helper to compute cosine similarity
        def cosine_sim(a, b):
            return sum(x * y for x, y in zip(a, b))

        # File tools should be more similar to each other than to email tool
        sim_file_file = cosine_sim(emb_read, emb_write)
        sim_file_email = cosine_sim(emb_read, emb_email)

        assert sim_file_file > sim_file_email

    def test_cache_functionality(self):
        """Test embedding caching."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="test_tool",
                server_id="core",
                description_1line="Test tool",
                description_full="A test tool",
                tags=["test"],
                risk_level="safe",
            )
        ]

        embedder.build_index(tools)

        # First embedding should cache
        embedding1 = embedder.embed_tool(tools[0])
        assert "test_tool" in embedder._cache

        # Get cached embedding
        cached = embedder.get_cached_embedding("test_tool")
        assert cached == embedding1

        # Clear cache
        embedder.clear_cache()
        assert "test_tool" not in embedder._cache

    def test_query_embedding(self):
        """Test query embedding generation."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="read_file",
                server_id="core",
                description_1line="Read files",
                description_full="Read files from disk",
                tags=["file", "read"],
                risk_level="safe",
            )
        ]

        embedder.build_index(tools)

        # Generate query embedding
        query_emb = embedder.embed_query("read files from disk")

        assert len(query_emb) > 0
        assert isinstance(query_emb, list)
        assert all(isinstance(x, float) for x in query_emb)

    def test_empty_query_embedding(self):
        """Test empty query returns zero vector."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="test",
                server_id="core",
                description_1line="Test",
                description_full="Test",
                tags=["test"],
                risk_level="safe",
            )
        ]

        embedder.build_index(tools)

        # Empty query
        emb_empty = embedder.embed_query("")
        assert all(x == 0.0 for x in emb_empty)

        # Whitespace only
        emb_whitespace = embedder.embed_query("   ")
        assert all(x == 0.0 for x in emb_whitespace)

    def test_empty_tool_description(self):
        """Test handling of tools with minimal content."""
        embedder = ToolEmbedder()

        # Tool with very minimal description
        tool = ToolRecord(
            tool_id="minimal",
            server_id="core",
            description_1line="X",
            description_full="X",
            tags=["x"],
            risk_level="safe",
        )

        embedder.build_index([tool])
        embedding = embedder.embed_tool(tool)

        # Should still produce valid embedding
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    def test_tf_idf_calculation(self):
        """Test TF-IDF score calculation."""
        embedder = ToolEmbedder()

        tools = [
            ToolRecord(
                tool_id="tool1",
                server_id="core",
                description_1line="file operation",
                description_full="file operation tool",
                tags=["file"],
                risk_level="safe",
            ),
            ToolRecord(
                tool_id="tool2",
                server_id="core",
                description_1line="network operation",
                description_full="network operation tool",
                tags=["network"],
                risk_level="safe",
            ),
        ]

        embedder.build_index(tools)

        # "operation" appears in both documents, should have lower IDF
        # "file" and "network" appear in only one, should have higher IDF
        assert embedder._idf_scores["operation"] < embedder._idf_scores["file"]
        assert embedder._idf_scores["operation"] < embedder._idf_scores["network"]

    def test_large_vocabulary(self):
        """Test embedder with larger vocabulary."""
        embedder = ToolEmbedder()

        # Create tools with diverse vocabulary
        tools = []
        for i in range(20):
            tools.append(
                ToolRecord(
                    tool_id=f"tool_{i}",
                    server_id="core",
                    description_1line=f"Tool number {i} for testing",
                    description_full=f"Extended description for tool {i} with unique words_{i}",
                    tags=[f"tag_{i}", "common"],
                    risk_level="safe",
                )
            )

        embedder.build_index(tools)

        # Vocabulary should be reasonably sized
        assert len(embedder._vocabulary) > 20
        assert len(embedder._vocabulary) < 200

        # All tools should have embeddings
        for tool in tools:
            embedding = embedder.get_cached_embedding(tool.tool_id)
            assert len(embedding) == len(embedder._vocabulary)

    def test_vector_normalization_edge_cases(self):
        """Test vector normalization with edge cases."""
        embedder = ToolEmbedder()

        # Zero vector
        zero_vec = embedder._normalize_vector([0.0, 0.0, 0.0])
        assert zero_vec == [0.0, 0.0, 0.0]

        # Unit vector (should stay the same)
        unit_vec = embedder._normalize_vector([1.0, 0.0, 0.0])
        assert abs(unit_vec[0] - 1.0) < 1e-6

        # Non-zero vector
        vec = embedder._normalize_vector([3.0, 4.0])
        magnitude = sum(x * x for x in vec) ** 0.5
        assert abs(magnitude - 1.0) < 1e-6
