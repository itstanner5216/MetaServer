"""
Tests for schema minimization edge cases (Phase 5 preview)

Validates that schema_min provides adequate information while
staying under token budget.
"""

import json

from src.meta_mcp.schemas.minimizer import minimize_schema


def test_large_schema_under_token_budget():
    """Test that large schemas are minimized to under 250 tokens."""
    large_schema = {
        "type": "object",
        "properties": {
            f"field_{i}": {
                "type": "string",
                "description": f"This is field {i} with a long description",
                "default": "example",
            }
            for i in range(100)
        },
        "required": ["field_0", "field_1"],
    }

    minimized = minimize_schema(large_schema, token_budget=200)

    token_estimate = len(json.dumps(minimized, separators=(",", ":"))) / 4
    assert token_estimate < 250, f"Minimized schema too large: ~{token_estimate} tokens"


def test_nested_objects_preserved():
    """Test that deeply nested objects preserve core structure."""
    nested_schema = {
        "type": "object",
        "properties": {
            "level1": {
                "type": "object",
                "properties": {
                    "level2": {
                        "type": "object",
                        "properties": {
                            "level3": {"type": "string", "description": "deep"}
                        },
                    }
                },
            }
        },
    }

    minimized = minimize_schema(nested_schema)

    assert minimized["properties"]["level1"]["type"] == "object"
    assert (
        minimized["properties"]["level1"]["properties"]["level2"]["properties"]["level3"][
            "type"
        ]
        == "string"
    )


def test_required_fields_preserved():
    """Test that required fields are preserved in minimization."""
    schema = {
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_field": {"type": "string"},
        },
        "required": ["required_field"],
    }

    minimized = minimize_schema(schema)

    assert "required_field" in minimized["properties"]
    assert "required" in minimized
    assert "required_field" in minimized["required"]


def test_enum_values_preserved():
    """Test that enum values are preserved (important for validation)."""
    schema = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "approved", "denied"],
            }
        },
    }

    minimized = minimize_schema(schema)

    assert "enum" in minimized["properties"]["status"]
    assert minimized["properties"]["status"]["enum"] == [
        "pending",
        "approved",
        "denied",
    ]


def test_array_schemas_minimized():
    """Test that array schemas are minimized correctly."""
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "number"},
                        "name": {"type": "string"},
                    },
                },
            }
        },
    }

    minimized = minimize_schema(schema)

    assert "items" in minimized["properties"]
    assert minimized["properties"]["items"]["type"] == "array"
    assert "properties" in minimized["properties"]["items"]["items"]
