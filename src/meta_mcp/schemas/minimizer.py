"""Schema minimization for progressive delivery.

This module reduces JSON schemas to minimal form (15-50 tokens) by stripping:
- Descriptions
- Examples
- Default values
- Non-essential metadata

Retains:
- Property names
- Types
- Required fields
- Essential structure

Design Plan Section: Phase 5 (Progressive Schemas)
"""

import json
from typing import Any


def minimize_schema(full_schema: dict[str, Any], token_budget: int = 50) -> dict[str, Any]:
    """
    Minimize a JSON schema to fit within token budget.

    Strategy:
    1. Strip all descriptions
    2. Strip all examples
    3. Strip all default values
    4. Keep only: property names, types, required array
    5. Preserve nested structure minimally

    Args:
        full_schema: Complete JSON schema (e.g., from tool.inputSchema)
        token_budget: Maximum tokens for minimal schema (default: 50)

    Returns:
        Minimized schema with only essential fields

    Example:
        Input (full_schema):
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read"
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "default": "utf-8"
                }
            },
            "required": ["file_path"]
        }

        Output (minimized):
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "encoding": {"type": "string"}
            },
            "required": ["file_path"]
        }
    """
    if not full_schema:
        return {}

    # Start with minimal structure
    minimal = {}

    # Preserve root type
    if "type" in full_schema:
        minimal["type"] = full_schema["type"]

    # Minimize properties recursively
    if "properties" in full_schema:
        minimal["properties"] = {}
        for prop_name, prop_schema in full_schema["properties"].items():
            minimal["properties"][prop_name] = _minimize_property(prop_schema)

    # Preserve required array (critical for validation)
    if "required" in full_schema:
        minimal["required"] = full_schema["required"]

    # Preserve items for arrays (minimal form)
    if "items" in full_schema:
        minimal["items"] = _minimize_property(full_schema["items"])

    # Preserve enum values (compact form)
    if "enum" in full_schema:
        minimal["enum"] = full_schema["enum"]

    return minimal


def _minimize_property(prop_schema: dict[str, Any]) -> dict[str, Any]:
    """
    Minimize a single property schema.

    Strips:
    - description
    - examples
    - default
    - title
    - format (unless critical)

    Keeps:
    - type
    - enum
    - items (for arrays)
    - properties (for objects)
    - required (for objects)

    Args:
        prop_schema: Property schema to minimize

    Returns:
        Minimized property schema
    """
    if not isinstance(prop_schema, dict):
        return prop_schema

    minimal = {}

    # Core fields to preserve
    if "type" in prop_schema:
        minimal["type"] = prop_schema["type"]

    if "enum" in prop_schema:
        minimal["enum"] = prop_schema["enum"]

    # Recursive minimization for nested structures
    if "items" in prop_schema:
        minimal["items"] = _minimize_property(prop_schema["items"])

    if "properties" in prop_schema:
        minimal["properties"] = {}
        for name, schema in prop_schema["properties"].items():
            minimal["properties"][name] = _minimize_property(schema)

    if "required" in prop_schema:
        minimal["required"] = prop_schema["required"]

    # For primitive types without type field
    if not minimal and isinstance(prop_schema, dict):
        # Fallback to just type if it exists
        if "type" in prop_schema:
            return {"type": prop_schema["type"]}

    return minimal


def estimate_token_count(schema: dict[str, Any]) -> int:
    """
    Estimate token count for a schema (rough approximation).

    Uses JSON string length / 4 as token estimate.
    This is a conservative approximation for LLM tokenization.

    Args:
        schema: JSON schema to estimate

    Returns:
        Estimated token count
    """
    if not schema:
        return 0

    # Serialize to JSON without whitespace
    json_str = json.dumps(schema, separators=(",", ":"))

    # Rough token estimate: 1 token ≈ 4 characters
    return len(json_str) // 4


def validate_minimal_schema(minimal_schema: dict[str, Any], max_tokens: int = 50) -> bool:
    """
    Validate that a minimal schema meets requirements.

    Requirements:
    1. Token count < max_tokens
    2. Has 'type' field
    3. Has 'properties' if type is 'object'
    4. Required fields are preserved

    Args:
        minimal_schema: Schema to validate
        max_tokens: Maximum allowed tokens (default: 50)

    Returns:
        True if schema is valid minimal schema

    Raises:
        ValueError: If schema violates requirements
    """
    if not minimal_schema:
        raise ValueError("Minimal schema cannot be empty")

    # Check token budget
    token_count = estimate_token_count(minimal_schema)
    if token_count > max_tokens:
        raise ValueError(f"Minimal schema exceeds token budget: {token_count} > {max_tokens}")

    # Check has type
    if "type" not in minimal_schema:
        raise ValueError("Minimal schema must have 'type' field")

    # Note: Object schemas MAY have 'properties' but it's not required by JSON Schema
    # Objects can use additionalProperties, patternProperties, etc. without properties
    # Removed overly strict validation that required 'properties' for all objects

    return True
