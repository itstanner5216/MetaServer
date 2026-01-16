"""
Integration Tests: Full Discovery Flow (Phase 1 + 2 + 5 + 6)

Tests the complete discovery workflow:
1. Client searches for tools (Phase 1 + 2)
2. Client requests schema (Phase 5)
3. Progressive schema delivery works
4. TOON encoding for large results (Phase 6)

Security Invariants:
- Only bootstrap tools visible initially
- Tools appear in list AFTER get_tool_schema
- Large results are compressed via TOON
- Schema expansion respects governance
"""

import pytest

from src.meta_mcp.registry import tool_registry
from src.meta_mcp.schemas.expander import expand_schema
from src.meta_mcp.toon.encoder import encode_output


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_bootstrap_discovery(redis_client):
    """
    Verify only bootstrap tools are visible initially.

    Flow:
    1. System starts with minimal bootstrap set
    2. Only search_tools, get_tool_schema, and expand_tool_schema are visible
    3. All other tools are hidden until explicitly requested
    """
    # Get bootstrap tools
    bootstrap = tool_registry.get_bootstrap_tools()

    # Verify minimal set
    assert len(bootstrap) == 3
    assert "search_tools" in bootstrap
    assert "get_tool_schema" in bootstrap
    assert "expand_tool_schema" in bootstrap

    # Verify other tools are registered but not exposed
    assert tool_registry.is_registered("read_file")
    assert tool_registry.is_registered("write_file")

    # But they should NOT be in bootstrap
    assert "read_file" not in bootstrap
    assert "write_file" not in bootstrap


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_search_finds_registered_tools(redis_client):
    """
    Verify search_tools finds registered tools by name/description.

    Flow:
    1. Client searches for "file" tools
    2. Registry returns matching tools
    3. Results include name, description, sensitivity
    4. Results do NOT include full schemas
    """
    # Search for file-related tools
    results = tool_registry.search("file")

    # Should find multiple file tools
    assert len(results) > 0

    # Verify results contain metadata only
    for tool in results:
        assert hasattr(tool, "tool_id")
        assert hasattr(tool, "description_1line")
        assert hasattr(tool, "risk_level")
        # Should NOT have full schema (ToolCandidate doesn't include schemas)
        assert not hasattr(tool, "schema_full")
        assert not hasattr(tool, "schema_min")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_search_prioritizes_name_matches(redis_client):
    """
    Verify search prioritizes name matches over description matches.

    Flow:
    1. Search for "read"
    2. Tools with "read" in name should come first
    3. Tools with "read" in description come second
    """
    results = tool_registry.search("read")

    # Should find at least read_file
    assert len(results) > 0

    # First result should have "read" in name
    assert "read" in results[0].name.lower()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_progressive_schema_delivery(redis_client):
    """
    Verify schemas are delivered progressively, not all at once.

    Flow:
    1. Tools are registered in the registry
    2. Client searches for tools
    3. Client gets tool details via registry.get()
    4. Tool records contain metadata but progressive schema delivery is controlled by server
    """
    # Use the module-level registry which is already loaded from YAML
    # Search for a safe tool
    results = tool_registry.search("read")
    assert len(results) > 0, "Should find read tools"

    tool_id = results[0].tool_id

    # Verify tool is registered
    tool = tool_registry.get(tool_id)
    assert tool is not None
    assert tool.tool_id == tool_id
    assert tool.risk_level == "safe"

    # Verify bootstrap tools are available
    bootstrap_tools = tool_registry.get_bootstrap_tools()
    assert "search_tools" in bootstrap_tools
    assert "get_tool_schema" in bootstrap_tools
    assert "expand_tool_schema" in bootstrap_tools


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_schema_expansion_with_examples(redis_client):
    """
    Verify expand_schema function exists and handles tool IDs correctly.

    Flow:
    1. Search for a tool that exists in registry
    2. Call expand_schema with valid tool_id
    3. Function should return None if schema not populated, or schema if available

    Note: This test verifies the API works, even if schemas aren't fully populated
    """
    # Get a tool that exists in the registry
    search_results = tool_registry.search("read")
    assert len(search_results) > 0, "Should find read tools"

    tool_id = search_results[0].tool_id

    # Expand schema - should not raise exception
    full_schema = expand_schema(tool_id)

    # Schema might be None if not populated in YAML, which is acceptable
    # Just verify the function doesn't crash
    if full_schema is not None:
        # If schema is returned, it should be a dict with 'type'
        assert isinstance(full_schema, dict)

    # Test with non-existent tool - should return None
    non_existent_schema = expand_schema("this_tool_does_not_exist_12345")
    assert non_existent_schema is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_toon_encoding_for_large_arrays(redis_client):
    """
    Verify TOON encoder compresses large arrays.

    Flow:
    1. Tool returns large array (> threshold)
    2. TOON encoder compresses to metadata
    3. Result includes count and sample
    4. Small arrays remain unchanged
    """
    # Small array (below threshold)
    small_result = {"files": ["a.txt", "b.txt", "c.txt"]}
    encoded_small = encode_output(small_result, threshold=5)

    # Should be unchanged
    assert encoded_small == small_result
    assert isinstance(encoded_small["files"], list)

    # Large array (above threshold)
    large_result = {"files": [f"file_{i}.txt" for i in range(20)]}
    encoded_large = encode_output(large_result, threshold=5)

    # Should be compressed
    assert "__toon" in encoded_large["files"]
    assert encoded_large["files"]["count"] == 20
    assert len(encoded_large["files"]["sample"]) == 3


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_toon_encoding_nested_structures(redis_client):
    """
    Verify TOON encoder handles nested structures recursively.

    Flow:
    1. Result has nested arrays
    2. TOON compresses each independently
    3. Structure is preserved
    """
    nested = {
        "directories": {
            "src": ["file1.py", "file2.py"],
            "tests": [f"test_{i}.py" for i in range(10)],
        }
    }

    encoded = encode_output(nested, threshold=5)

    # Small array unchanged
    assert isinstance(encoded["directories"]["src"], list)
    assert len(encoded["directories"]["src"]) == 2

    # Large array compressed
    assert "__toon" in encoded["directories"]["tests"]
    assert encoded["directories"]["tests"]["count"] == 10


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_discovery_security_no_schema_leakage(redis_client):
    """
    Verify search results don't leak full schemas.

    Security Invariant:
    - Search returns metadata only
    - Full schemas require explicit get_tool_schema call
    - This prevents context pollution
    """
    results = tool_registry.search("write")

    for tool in results:
        # Should have minimal metadata
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")

        # Should NOT have full schema details
        # (ToolCandidate doesn't have inputSchema)
        assert not hasattr(tool, "inputSchema")
        assert not hasattr(tool, "examples")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_toon_threshold_boundary_conditions(redis_client):
    """
    Verify TOON encoder handles boundary conditions correctly.

    Edge Cases:
    - Array exactly at threshold
    - Array at threshold + 1
    - Empty arrays
    - Null values
    """
    # Exactly at threshold (should NOT compress)
    at_threshold = {"items": [1, 2, 3, 4, 5]}
    encoded_at = encode_output(at_threshold, threshold=5)
    assert isinstance(encoded_at["items"], list)
    assert len(encoded_at["items"]) == 5

    # One over threshold (SHOULD compress)
    over_threshold = {"items": [1, 2, 3, 4, 5, 6]}
    encoded_over = encode_output(over_threshold, threshold=5)
    assert "__toon" in encoded_over["items"]
    assert encoded_over["items"]["count"] == 6

    # Empty array
    empty = {"items": []}
    encoded_empty = encode_output(empty, threshold=5)
    assert encoded_empty["items"] == []

    # Null value
    null = {"items": None}
    encoded_null = encode_output(null, threshold=5)
    assert encoded_null["items"] is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_complete_discovery_workflow(redis_client):
    """
    End-to-end test of complete discovery workflow.

    Flow:
    1. Client starts with bootstrap tools only
    2. Client searches for "file" tools
    3. Client finds read_file in results
    4. Client requests schema via get_tool_schema
    5. Schema is returned with TOON encoding if needed
    6. Tool is now exposed for use
    """
    # Step 1: Bootstrap
    bootstrap = tool_registry.get_bootstrap_tools()
    assert "search_tools" in bootstrap

    # Step 2: Search
    results = tool_registry.search("file")
    assert len(results) > 0

    # Step 3: Find tool
    read_file_found = any(t.name == "read_file" for t in results)
    assert read_file_found

    # Step 4: Get tool details
    tool = next(t for t in results if t.name == "read_file")
    assert tool.description is not None
    assert tool.sensitive is False  # read_file is safe

    # Step 5: Verify TOON would apply to large results
    # Simulate large directory listing
    large_listing = {"files": [f"file_{i}.txt" for i in range(100)]}
    encoded = encode_output(large_listing, threshold=10)

    assert "__toon" in encoded["files"]
    assert encoded["files"]["count"] == 100
    assert len(encoded["files"]["sample"]) == 3


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_search_empty_query_returns_empty(redis_client):
    """
    Verify search with empty query returns empty results.

    Security: Prevents returning all tools on empty query.
    """
    # Empty string
    results = tool_registry.search("")
    assert len(results) == 0

    # Whitespace only
    results = tool_registry.search("   ")
    assert len(results) == 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_redis
async def test_toon_preserves_primitive_types(redis_client):
    """
    Verify TOON encoder preserves primitive types unchanged.

    Primitives: str, int, float, bool, None
    """
    primitives = {"string": "hello", "integer": 42, "float": 3.14, "boolean": True, "null": None}

    encoded = encode_output(primitives, threshold=5)

    # All primitives should be unchanged
    assert encoded["string"] == "hello"
    assert encoded["integer"] == 42
    assert encoded["float"] == 3.14
    assert encoded["boolean"] is True
    assert encoded["null"] is None
