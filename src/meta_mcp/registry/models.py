"""Data models for tool registry."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ServerRecord:
    """
    Static metadata for an MCP server.

    Design Plan Section 3.2
    """

    server_id: str  # "core_tools", "admin_tools"
    description: str  # 1-line summary
    risk_level: str  # "safe", "sensitive", "dangerous"
    tags: list[str] = field(default_factory=list)
    embedding_vector: list[float] | None = None  # Phase 2


@dataclass
class ToolRecord:
    """
    Static metadata for a tool.

    Design Plan Section 3.1

    Invariants:
    - tool_id must be unique across all servers
    - risk_level must be one of: safe, sensitive, dangerous
    - description_1line must not be empty
    - tags list must have at least one element
    - schema_min token count must be < 50 (Phase 5, not enforced yet)
    """

    tool_id: str  # "read_file", "write_file"
    server_id: str  # Parent server
    description_1line: str  # For search results
    description_full: str  # For schema delivery
    tags: list[str]  # ["file", "read", "workspace"]
    risk_level: str  # "safe", "sensitive", "dangerous"
    requires_permission: bool = False
    required_scopes: list[str] = field(default_factory=list)  # Permission scopes for approval

    # Progressive Schemas (Phase 5)
    schema_min: dict[str, Any] | None = None  # 15-50 tokens
    schema_full: dict[str, Any] | None = None  # Complete schema

    # Semantic Retrieval (Phase 2)
    embedding_vector: list[float] | None = None

    # Metadata
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate_invariants(self) -> bool:
        """
        Validate ToolRecord invariants.

        Returns:
            True if all invariants are satisfied

        Raises:
            AssertionError: If any invariant is violated
        """
        assert self.risk_level in ["safe", "sensitive", "dangerous"], (
            f"risk_level must be one of [safe, sensitive, dangerous], got '{self.risk_level}'"
        )
        assert len(self.description_1line) > 0, "description_1line must not be empty"
        assert len(self.tags) > 0, "tags list must have at least one element"
        return True


@dataclass
class ToolCandidate:
    """
    Tool candidate returned by search (no schema).

    Design Plan Section 3.3

    This is what search results return - metadata only, no schemas.
    Model must call get_tool_schema() to access a tool.
    """

    tool_id: str
    server_id: str
    description_1line: str
    tags: list[str]
    risk_level: str
    relevance_score: float = 0.0  # Semantic similarity (Phase 2)

    # IMPORTANT: Does NOT include schema fields
    # schema_min and schema_full are intentionally omitted

    @property
    def name(self) -> str:
        """
        Compatibility property: maps to tool_id.

        Provided for API compatibility with code expecting .name attribute.
        """
        return self.tool_id

    @property
    def description(self) -> str:
        """
        Compatibility property: maps to description_1line.

        Provided for API compatibility with code expecting .description attribute.
        """
        return self.description_1line

    @property
    def sensitive(self) -> bool:
        """
        Compatibility property: maps risk_level to boolean sensitivity flag.

        Returns True if risk_level is not "safe", False otherwise.
        Provided for API compatibility with code expecting .sensitive attribute.
        """
        return self.risk_level != "safe"
