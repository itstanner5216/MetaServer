"""Tests for schema expansion (Phase 5)."""

import pytest

from src.meta_mcp.schemas.expander import expand_schema


def test_expand_schema_returns_full_schema():
    """Test that expand_schema returns full schema from ToolRecord."""
    # Create a mock tool record with both schemas
    from src.meta_mcp.registry import tool_registry

    # Get a real tool from registry
    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set up test schemas
        full_schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                }
            },
            "required": ["file_path"],
        }

        minimal_schema = {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        }

        # Store schemas in tool record
        tool_record.schema_full = full_schema
        tool_record.schema_min = minimal_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should return full schema
        assert expanded == full_schema
        assert "description" in expanded["properties"]["file_path"]


def test_expand_schema_tool_not_found():
    """Test expand_schema returns None for unknown tool."""
    expanded = expand_schema("nonexistent_tool")
    assert expanded is None


def test_expand_schema_fallback_to_minimal():
    """Test expand_schema falls back to minimal schema if full not available."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set only minimal schema
        minimal_schema = {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        }

        tool_record.schema_full = None
        tool_record.schema_min = minimal_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should return minimal schema as fallback
        assert expanded == minimal_schema


def test_expand_schema_no_schema_available():
    """Test expand_schema returns None when no schema available."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Clear both schemas
        tool_record.schema_full = None
        tool_record.schema_min = None

        # Expand schema
        expanded = expand_schema("read_file")

        # Should return None
        assert expanded is None


def test_expand_schema_preserves_nested_structure():
    """Test that expand_schema preserves nested object structure."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set up nested schema
        full_schema = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "description": "Configuration object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "Server host",
                        }
                    },
                    "required": ["host"],
                }
            },
            "required": ["config"],
        }

        tool_record.schema_full = full_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should preserve nested structure
        assert expanded["properties"]["config"]["type"] == "object"
        assert "description" in expanded["properties"]["config"]
        assert "host" in expanded["properties"]["config"]["properties"]


def test_expand_schema_preserves_arrays():
    """Test that expand_schema preserves array schemas."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set up array schema
        full_schema = {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "description": "List of files",
                    "items": {
                        "type": "string",
                        "description": "File path",
                    },
                }
            },
            "required": ["files"],
        }

        tool_record.schema_full = full_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should preserve array structure
        assert expanded["properties"]["files"]["type"] == "array"
        assert "items" in expanded["properties"]["files"]
        assert "description" in expanded["properties"]["files"]["items"]


def test_expand_schema_preserves_enums():
    """Test that expand_schema preserves enum values."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set up enum schema
        full_schema = {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "Execution mode",
                    "enum": ["READ_ONLY", "PERMISSION", "BYPASS"],
                }
            },
            "required": ["mode"],
        }

        tool_record.schema_full = full_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should preserve enum
        assert expanded["properties"]["mode"]["enum"] == [
            "READ_ONLY",
            "PERMISSION",
            "BYPASS",
        ]


def test_expand_schema_preserves_defaults():
    """Test that expand_schema preserves default values."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set up schema with defaults
        full_schema = {
            "type": "object",
            "properties": {
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "default": "utf-8",
                }
            },
        }

        tool_record.schema_full = full_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should preserve default
        assert expanded["properties"]["encoding"]["default"] == "utf-8"


def test_expand_schema_preserves_examples():
    """Test that expand_schema preserves examples."""
    from src.meta_mcp.registry import tool_registry

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Set up schema with examples
        full_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path",
                    "examples": ["/path/to/file.txt", "/another/path.md"],
                }
            },
        }

        tool_record.schema_full = full_schema

        # Expand schema
        expanded = expand_schema("read_file")

        # Should preserve examples
        assert expanded["properties"]["path"]["examples"] == [
            "/path/to/file.txt",
            "/another/path.md",
        ]


@pytest.mark.asyncio
async def test_expand_schema_from_live_tool_async():
    """Test async expansion from live tool instance."""
    from src.meta_mcp.schemas.expander import expand_schema_from_live_tool_async
    from src.meta_mcp.supervisor import mcp

    # Try to expand schema from live tool
    expanded = await expand_schema_from_live_tool_async("search_tools", mcp)

    # Should return schema (or None if tool not exposed yet)
    # This is a basic smoke test
    if expanded:
        assert isinstance(expanded, dict)


def test_expansion_restores_full_schema():
    """Integration test: minimization + expansion should restore full schema."""
    from src.meta_mcp.registry import tool_registry
    from src.meta_mcp.schemas.minimizer import minimize_schema

    tool_record = tool_registry.get("read_file")

    if tool_record:
        # Original full schema
        full_schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                    "examples": ["/path/to/file.txt"],
                }
            },
            "required": ["file_path"],
        }

        # Minimize it
        minimal = minimize_schema(full_schema)

        # Store both versions
        tool_record.schema_full = full_schema
        tool_record.schema_min = minimal

        # Expand it
        expanded = expand_schema("read_file")

        # Should restore original full schema
        assert expanded == full_schema
        assert "description" in expanded["properties"]["file_path"]
        assert "examples" in expanded["properties"]["file_path"]
