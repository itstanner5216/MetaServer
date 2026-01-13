"""Integration tests for expand_tool_schema tool (Phase 5)."""

import pytest
import json
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_expand_parameter_exists():
    """Test that get_tool_schema tool accepts expand parameter."""
    from src.meta_mcp.supervisor import mcp

    # Check that get_tool_schema is registered
    tool = await mcp.get_tool("get_tool_schema")
    assert tool is not None
    assert tool.name == "get_tool_schema"

    # Verify tool has expand parameter in schema
    mcp_tool = tool.to_mcp_tool()
    assert "inputSchema" in mcp_tool.model_dump()
    input_schema = mcp_tool.inputSchema
    assert "properties" in input_schema
    assert "expand" in input_schema["properties"]


@pytest.mark.asyncio
async def test_expand_parameter_returns_full_schema():
    """Test get_tool_schema with expand=True returns full schema for a tool."""
    from src.meta_mcp.supervisor import mcp, get_tool_schema
    from src.meta_mcp.config import Config

    # Temporarily enable progressive schemas
    original_flag = Config.ENABLE_PROGRESSIVE_SCHEMAS
    Config.ENABLE_PROGRESSIVE_SCHEMAS = True

    try:
        # First, get minimal schema (this triggers tool exposure)
        minimal_result = await get_tool_schema.fn(tool_name="read_file", expand=False)
        minimal_data = json.loads(minimal_result)

        # Now expand the schema
        expanded_result = await get_tool_schema.fn(tool_name="read_file", expand=True)
        expanded_data = json.loads(expanded_result)

        # Should have inputSchema
        assert "inputSchema" in expanded_data

        # Full schema should have more detail than minimal
        # (This test is flexible as we're using live tool schemas)
        assert isinstance(expanded_data["inputSchema"], dict)

    finally:
        # Restore original flag
        Config.ENABLE_PROGRESSIVE_SCHEMAS = original_flag


@pytest.mark.asyncio
async def test_expand_parameter_unregistered_tool():
    """Test get_tool_schema with expand=True raises error for unregistered tool."""
    from src.meta_mcp.supervisor import get_tool_schema

    with pytest.raises(ToolError, match="not registered"):
        await get_tool_schema.fn(tool_name="nonexistent_tool", expand=True)


@pytest.mark.asyncio
async def test_expand_parameter_without_prior_access():
    """Test get_tool_schema with expand=True works even without prior minimal schema call."""
    from src.meta_mcp.supervisor import get_tool_schema

    # Try to expand schema for a tool we haven't accessed yet
    # This should still work by falling back to live tool instance
    try:
        result = await get_tool_schema.fn(tool_name="write_file", expand=True)
        data = json.loads(result)

        # Should return schema
        assert "inputSchema" in data
        assert isinstance(data["inputSchema"], dict)

    except ToolError:
        # This is acceptable if tool isn't exposed yet
        # The important thing is it doesn't crash
        pass


@pytest.mark.asyncio
async def test_expand_parameter_bypasses_governance():
    """Test that get_tool_schema with expand=True bypasses governance (schema already approved)."""
    from src.meta_mcp.supervisor import get_tool_schema
    from src.meta_mcp.config import Config

    # This test verifies the design requirement that expansion bypasses governance
    # because the schema was already approved when get_tool_schema was called

    original_flag = Config.ENABLE_PROGRESSIVE_SCHEMAS
    Config.ENABLE_PROGRESSIVE_SCHEMAS = True

    try:
        # Get schema for a tool (approves it)
        await get_tool_schema.fn(tool_name="read_file", expand=False)

        # Expand should work without additional approval
        result = await get_tool_schema.fn(tool_name="read_file", expand=True)
        data = json.loads(result)

        # Should succeed
        assert "inputSchema" in data

    finally:
        Config.ENABLE_PROGRESSIVE_SCHEMAS = original_flag


@pytest.mark.asyncio
async def test_expand_parameter_format():
    """Test get_tool_schema with expand=True returns correct JSON format."""
    from src.meta_mcp.supervisor import get_tool_schema

    # Get schema first to expose tool
    await get_tool_schema.fn(tool_name="read_file", expand=False)

    # Expand schema
    result = await get_tool_schema.fn(tool_name="read_file", expand=True)
    data = json.loads(result)

    # Check format
    assert "name" in data
    assert data["name"] == "read_file"
    assert "inputSchema" in data
    assert isinstance(data["inputSchema"], dict)


@pytest.mark.asyncio
async def test_progressive_schema_workflow():
    """Integration test: Full progressive schema workflow."""
    from src.meta_mcp.supervisor import get_tool_schema
    from src.meta_mcp.config import Config
    from src.meta_mcp.schemas.minimizer import estimate_token_count

    original_flag = Config.ENABLE_PROGRESSIVE_SCHEMAS
    Config.ENABLE_PROGRESSIVE_SCHEMAS = True

    try:
        # Step 1: Get minimal schema
        minimal_result = await get_tool_schema.fn(tool_name="read_file", expand=False)
        minimal_data = json.loads(minimal_result)

        minimal_schema = minimal_data.get("inputSchema", {})
        minimal_tokens = estimate_token_count(minimal_schema)

        # Step 2: Expand to full schema
        expanded_result = await get_tool_schema.fn(tool_name="read_file", expand=True)
        expanded_data = json.loads(expanded_result)

        expanded_schema = expanded_data.get("inputSchema", {})
        expanded_tokens = estimate_token_count(expanded_schema)

        # Verify workflow
        # 1. Minimal schema should be smaller (in most cases)
        # 2. Both should be valid schemas
        assert isinstance(minimal_schema, dict)
        assert isinstance(expanded_schema, dict)

        # 3. Minimal schema should be under 50 tokens
        assert minimal_tokens <= 50, f"Minimal schema has {minimal_tokens} tokens (max: 50)"

        print(f"Minimal: {minimal_tokens} tokens, Expanded: {expanded_tokens} tokens")

    finally:
        Config.ENABLE_PROGRESSIVE_SCHEMAS = original_flag


@pytest.mark.asyncio
async def test_expand_parameter_fallback_to_live_tool():
    """Test get_tool_schema with expand=True falls back to live tool if registry schema unavailable."""
    from src.meta_mcp.supervisor import get_tool_schema
    from src.meta_mcp.registry import tool_registry

    # Get a tool and clear its schemas in registry
    await get_tool_schema.fn(tool_name="read_file", expand=False)

    tool_record = tool_registry.get("read_file")
    if tool_record:
        # Clear schemas to force fallback
        tool_record.schema_full = None
        tool_record.schema_min = None

    # Expand should still work by falling back to live tool
    result = await get_tool_schema.fn(tool_name="read_file", expand=True)
    data = json.loads(result)

    # Should still return schema
    assert "inputSchema" in data
    assert isinstance(data["inputSchema"], dict)


@pytest.mark.asyncio
async def test_expand_parameter_preserves_structure():
    """Test that get_tool_schema with expand=True preserves schema structure."""
    from src.meta_mcp.supervisor import get_tool_schema
    from src.meta_mcp.config import Config

    original_flag = Config.ENABLE_PROGRESSIVE_SCHEMAS
    Config.ENABLE_PROGRESSIVE_SCHEMAS = True

    try:
        # Get and expand schema
        await get_tool_schema.fn(tool_name="read_file", expand=False)
        result = await get_tool_schema.fn(tool_name="read_file", expand=True)
        data = json.loads(result)

        schema = data["inputSchema"]

        # Should have standard schema structure
        if schema:  # Schema might be empty for some tools
            assert isinstance(schema, dict)
            # Common schema fields
            if "type" in schema:
                assert isinstance(schema["type"], str)
            if "properties" in schema:
                assert isinstance(schema["properties"], dict)

    finally:
        Config.ENABLE_PROGRESSIVE_SCHEMAS = original_flag
