from src.meta_mcp.registry.models import ToolRecord
from src.meta_mcp.retrieval.embedder import ToolEmbedder


def test_cache_preallocation():
    tools = [
        ToolRecord(
            tool_id=f"tool_{i}",
            server_id="test_server",
            description_1line="Test tool",
            description_full="Test tool description",
            tags=["test"],
            risk_level="safe",
        )
        for i in range(3)
    ]

    embedder = ToolEmbedder()
    embedder.build_index(tools)

    assert len(embedder._cache) == 3
    assert all(embedder._cache[tool.tool_id] is not None for tool in tools)
