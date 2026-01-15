"""Tests for schema minimization (Phase 5)."""

import pytest

from src.meta_mcp.schemas.minimizer import (
    estimate_token_count,
    minimize_schema,
    validate_minimal_schema,
)


def test_minimize_simple_schema():
    """Test minimization of a simple object schema."""
    full_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to read",
                "examples": ["/path/to/file.txt"],
            },
            "encoding": {
                "type": "string",
                "description": "File encoding to use",
                "default": "utf-8",
            },
        },
        "required": ["file_path"],
    }

    minimal = minimize_schema(full_schema)

    # Check structure is preserved
    assert minimal["type"] == "object"
    assert "properties" in minimal
    assert "required" in minimal

    # Check descriptions are stripped
    assert "description" not in minimal["properties"]["file_path"]
    assert "description" not in minimal["properties"]["encoding"]

    # Check examples and defaults are stripped
    assert "examples" not in minimal["properties"]["file_path"]
    assert "default" not in minimal["properties"]["encoding"]

    # Check types are preserved
    assert minimal["properties"]["file_path"]["type"] == "string"
    assert minimal["properties"]["encoding"]["type"] == "string"

    # Check required is preserved
    assert minimal["required"] == ["file_path"]


def test_minimize_nested_schema():
    """Test minimization of nested object schema."""
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
                        "default": "localhost",
                    },
                    "port": {
                        "type": "integer",
                        "description": "Server port",
                        "default": 8080,
                    },
                },
                "required": ["host"],
            }
        },
        "required": ["config"],
    }

    minimal = minimize_schema(full_schema)

    # Check nested structure is preserved
    assert minimal["type"] == "object"
    assert "config" in minimal["properties"]
    assert minimal["properties"]["config"]["type"] == "object"

    # Check nested properties are minimized
    assert "host" in minimal["properties"]["config"]["properties"]
    assert "port" in minimal["properties"]["config"]["properties"]

    # Check nested descriptions are stripped
    assert "description" not in minimal["properties"]["config"]
    assert "description" not in minimal["properties"]["config"]["properties"]["host"]
    assert "description" not in minimal["properties"]["config"]["properties"]["port"]

    # Check nested defaults are stripped
    assert "default" not in minimal["properties"]["config"]["properties"]["host"]
    assert "default" not in minimal["properties"]["config"]["properties"]["port"]

    # Check nested required is preserved
    assert minimal["properties"]["config"]["required"] == ["host"]


def test_minimize_array_schema():
    """Test minimization of array schema."""
    full_schema = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": "List of file paths",
                "items": {
                    "type": "string",
                    "description": "File path",
                },
            }
        },
        "required": ["files"],
    }

    minimal = minimize_schema(full_schema)

    # Check array structure is preserved
    assert minimal["properties"]["files"]["type"] == "array"
    assert "items" in minimal["properties"]["files"]

    # Check items are minimized
    assert minimal["properties"]["files"]["items"]["type"] == "string"
    assert "description" not in minimal["properties"]["files"]["items"]


def test_minimize_enum_schema():
    """Test minimization preserves enum values."""
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

    minimal = minimize_schema(full_schema)

    # Check enum is preserved
    assert minimal["properties"]["mode"]["enum"] == [
        "READ_ONLY",
        "PERMISSION",
        "BYPASS",
    ]
    assert minimal["properties"]["mode"]["type"] == "string"

    # Check description is stripped
    assert "description" not in minimal["properties"]["mode"]


def test_minimize_empty_schema():
    """Test minimization of empty schema."""
    minimal = minimize_schema({})
    assert minimal == {}


def test_minimize_produces_schemas_under_50_tokens():
    """Test that minimized schemas are under 50 token budget."""
    # Complex schema with many properties
    full_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to operate on",
            },
            "content": {
                "type": "string",
                "description": "Content to write to file",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding",
                "default": "utf-8",
            },
            "mode": {
                "type": "string",
                "description": "Write mode",
                "enum": ["write", "append"],
                "default": "write",
            },
        },
        "required": ["path", "content"],
    }

    minimal = minimize_schema(full_schema, token_budget=50)

    # Estimate token count
    token_count = estimate_token_count(minimal)

    # Should be under 50 tokens
    assert token_count < 50, f"Schema has {token_count} tokens (max: 50)"


def test_estimate_token_count():
    """Test token count estimation."""
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}

    token_count = estimate_token_count(schema)

    # Should be a reasonable estimate (> 0)
    assert token_count > 0

    # Empty schema should have 0 tokens
    assert estimate_token_count({}) == 0


def test_validate_minimal_schema_success():
    """Test validation of valid minimal schema."""
    minimal = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    }

    # Should pass validation
    assert validate_minimal_schema(minimal, max_tokens=50) is True


def test_validate_minimal_schema_missing_type():
    """Test validation fails for schema without type."""
    minimal = {
        "properties": {
            "name": {"type": "string"},
        }
    }

    with pytest.raises(ValueError, match="must have 'type' field"):
        validate_minimal_schema(minimal)


def test_validate_minimal_schema_object_without_properties():
    """Test validation fails for object schema without properties."""
    minimal = {
        "type": "object",
    }

    with pytest.raises(ValueError, match="must have 'properties' field"):
        validate_minimal_schema(minimal)


def test_validate_minimal_schema_exceeds_token_budget():
    """Test validation fails for schema exceeding token budget."""
    # Create a schema that's too large
    minimal = {
        "type": "object",
        "properties": {f"property_{i}": {"type": "string"} for i in range(100)},
    }

    with pytest.raises(ValueError, match="exceeds token budget"):
        validate_minimal_schema(minimal, max_tokens=50)


def test_validate_minimal_schema_empty():
    """Test validation fails for empty schema."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_minimal_schema({})


def test_minimize_preserves_required_fields():
    """Test that minimize_schema preserves all required fields."""
    full_schema = {
        "type": "object",
        "properties": {
            "required_field": {
                "type": "string",
                "description": "This is required",
            },
            "optional_field": {
                "type": "string",
                "description": "This is optional",
            },
        },
        "required": ["required_field"],
    }

    minimal = minimize_schema(full_schema)

    # Required array must be preserved exactly
    assert minimal["required"] == ["required_field"]

    # Both properties should still exist (just minimized)
    assert "required_field" in minimal["properties"]
    assert "optional_field" in minimal["properties"]


def test_real_world_read_file_schema():
    """Test minimization on real read_file schema."""
    # Approximate read_file schema
    full_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to read (absolute or relative to workspace)",
            }
        },
        "required": ["file_path"],
    }

    minimal = minimize_schema(full_schema)

    # Should be very compact
    token_count = estimate_token_count(minimal)
    assert token_count < 30  # Should be well under budget

    # Should preserve structure
    assert minimal == {
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"],
    }


def test_real_world_write_file_schema():
    """Test minimization on real write_file schema."""
    # Approximate write_file schema
    full_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to write (absolute or relative to workspace)",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    }

    minimal = minimize_schema(full_schema)

    # Should be compact
    token_count = estimate_token_count(minimal)
    assert token_count < 40

    # Should preserve both required fields
    assert set(minimal["required"]) == {"file_path", "content"}
