#!/usr/bin/env python3
"""
Quick verification script for Phase 2: Semantic Retrieval
"""
import sys
sys.path.insert(0, '/home/tanner/Projects/MCPServer')

from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.registry.registry import ToolRegistry
from src.meta_mcp.retrieval.embedder import ToolEmbedder
from src.meta_mcp.retrieval.search import SemanticSearch
from src.meta_mcp.config import Config

def test_embedder():
    """Test basic embedder functionality."""
    print("Testing ToolEmbedder...")

    embedder = ToolEmbedder()

    # Create sample tools
    tools = [
        ToolRecord(
            tool_id="read_file",
            server_id="core",
            description_1line="Read files from disk",
            description_full="Read text and binary files from the file system",
            tags=["file", "read", "disk"],
            risk_level="safe"
        ),
        ToolRecord(
            tool_id="write_file",
            server_id="core",
            description_1line="Write files to disk",
            description_full="Write text and binary files to the file system",
            tags=["file", "write", "disk"],
            risk_level="sensitive"
        )
    ]

    # Build index
    embedder.build_index(tools)

    # Test embedding
    emb1 = embedder.embed_tool(tools[0])
    assert len(emb1) > 0, "Embedding should not be empty"
    assert all(isinstance(x, float) for x in emb1), "Embedding should be floats"

    # Test query embedding
    query_emb = embedder.embed_query("read files")
    assert len(query_emb) > 0, "Query embedding should not be empty"

    print("  ✓ ToolEmbedder working correctly")
    return True

def test_semantic_search():
    """Test semantic search functionality."""
    print("Testing SemanticSearch...")

    registry = ToolRegistry()

    # Add sample tools
    tools = [
        ToolRecord(
            tool_id="read_file",
            server_id="core",
            description_1line="Read files from disk",
            description_full="Read text and binary files",
            tags=["file", "read"],
            risk_level="safe"
        ),
        ToolRecord(
            tool_id="send_email",
            server_id="network",
            description_1line="Send email messages",
            description_full="Send email to recipients",
            tags=["email", "send"],
            risk_level="sensitive"
        )
    ]

    for tool in tools:
        registry._tools[tool.tool_id] = tool

    # Create searcher
    searcher = SemanticSearch(registry)

    # Test search
    results = searcher.search("read files")
    assert len(results) > 0, "Search should return results"
    assert results[0].tool_id == "read_file", "Most relevant tool should be read_file"

    print("  ✓ SemanticSearch working correctly")
    return True

def test_config_flag():
    """Test configuration flag."""
    print("Testing Config...")

    # Check flag exists
    assert hasattr(Config, 'ENABLE_SEMANTIC_RETRIEVAL'), "Config should have ENABLE_SEMANTIC_RETRIEVAL flag"
    assert isinstance(Config.ENABLE_SEMANTIC_RETRIEVAL, bool), "Flag should be boolean"
    assert Config.ENABLE_SEMANTIC_RETRIEVAL is False, "Flag should default to False"

    print("  ✓ Config flag correct")
    return True

def test_registry_integration():
    """Test registry integration."""
    print("Testing Registry integration...")

    registry = ToolRegistry()

    # Add sample tools
    tools = [
        ToolRecord(
            tool_id="test_tool",
            server_id="core",
            description_1line="Test tool",
            description_full="A test tool",
            tags=["test"],
            risk_level="safe"
        )
    ]

    for tool in tools:
        registry._tools[tool.tool_id] = tool

    # Test keyword search (default)
    Config.ENABLE_SEMANTIC_RETRIEVAL = False
    results = registry.search("test")
    assert len(results) > 0, "Keyword search should work"

    # Test semantic search (when enabled)
    Config.ENABLE_SEMANTIC_RETRIEVAL = True
    try:
        results = registry.search("test")
        assert len(results) > 0, "Semantic search should work"
        print("  ✓ Registry integration working correctly")
    finally:
        Config.ENABLE_SEMANTIC_RETRIEVAL = False

    return True

def main():
    """Run all verification tests."""
    print("\n" + "="*60)
    print("Phase 2: Semantic Retrieval Verification")
    print("="*60 + "\n")

    try:
        test_embedder()
        test_semantic_search()
        test_config_flag()
        test_registry_integration()

        print("\n" + "="*60)
        print("✓ All Phase 2 components verified successfully!")
        print("="*60 + "\n")
        return 0

    except Exception as e:
        print(f"\n✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
