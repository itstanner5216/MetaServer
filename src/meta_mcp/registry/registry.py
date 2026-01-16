"""Tool registry implementation."""

import asyncio
import os
from pathlib import Path

import yaml

from ..governance.policy import evaluate_policy
from ..state import governance_state
from .models import (
    AllowedInMode,
    ServerRecord,
    ToolCandidate,
    ToolRecord,
    extract_schema_hint,
)


def _resolve_governance_mode():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(governance_state.get_mode())
    return governance_state._default_mode()


class ToolRegistry:
    """
    Static tool registry loaded from YAML.

    Replaces the dynamic discovery.ToolRegistry for Phase 1+.

    Features:
    - Static tool definitions from YAML
    - Simple keyword search (replaced by semantic search in Phase 2)
    - Bootstrap tool tracking
    - Progressive discovery support
    """

    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: dict[str, ToolRecord] = {}
        self._servers: dict[str, ServerRecord] = {}
        self._bootstrap_tools = {"search_tools", "get_tool_schema"}

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ToolRegistry":
        """
        Load registry from YAML file.

        Args:
            yaml_path: Path to tools.yaml configuration file

        Returns:
            Initialized ToolRegistry instance

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        registry = cls()

        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            raise FileNotFoundError(f"Registry YAML not found: {yaml_path}")

        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        # Validate YAML structure
        if not isinstance(data, dict):
            raise ValueError(f"Invalid YAML structure: expected dict, got {type(data).__name__}")

        if "servers" in data and not isinstance(data["servers"], list):
            raise ValueError("'servers' must be a list")

        if "tools" in data and not isinstance(data["tools"], list):
            raise ValueError("'tools' must be a list")

        # Load servers
        for server_data in data.get("servers", []):
            server = ServerRecord(**server_data)
            registry._servers[server.server_id] = server

        # Load tools
        for tool_data in data.get("tools", []):
            tool = ToolRecord(**tool_data)
            tool.validate_invariants()
            registry._tools[tool.tool_id] = tool

        return registry

    def is_registered(self, tool_id: str) -> bool:
        """
        Check if tool is registered.

        Args:
            tool_id: Tool identifier

        Returns:
            True if tool is registered
        """
        return tool_id in self._tools

    def get(self, tool_id: str) -> ToolRecord | None:
        """
        Get tool record by ID.

        Args:
            tool_id: Tool identifier

        Returns:
            ToolRecord if found, None otherwise
        """
        return self._tools.get(tool_id)

    def add(self, tool: ToolRecord) -> None:
        """
        Add tool to registry.

        This method is primarily used by test fixtures. In production,
        tool registration happens via config/tools.yaml.

        Args:
            tool: ToolRecord to add to registry

        Raises:
            ValueError: If tool fails validation
        """
        tool.validate_invariants()
        self._tools[tool.tool_id] = tool

    def search(self, query: str) -> list[ToolCandidate]:
        """
        Search for tools using semantic or keyword matching.

        Uses semantic search if ENABLE_SEMANTIC_RETRIEVAL is True,
        otherwise falls back to keyword matching.

        Returns ToolCandidate objects (no schema fields).

        Args:
            query: Search query string

        Returns:
            List of ToolCandidate objects ranked by relevance
        """
        if not query or not query.strip():
            return []

        # Phase 2: Use semantic search if enabled
        from ..config import Config

        if Config.ENABLE_SEMANTIC_RETRIEVAL:
            try:
                from ..retrieval import SemanticSearch

                searcher = SemanticSearch(self)
                return searcher.search(query, limit=8)
            except ImportError:
                # Expected if retrieval module not available
                import logging

                logging.debug("Semantic search not available, falling back to keyword search")
            except Exception as e:
                # Unexpected error - log it
                import logging

                logging.error(f"Semantic search failed: {e}", exc_info=True)

        # Fallback: Original keyword matching
        query_lower = query.lower().strip()
        results = []
        mode = _resolve_governance_mode()

        for tool in self._tools.values():
            # Simple keyword matching in tool_id, description and tags
            score = 0.0

            if query_lower in tool.tool_id.lower() or query_lower in tool.description_1line.lower():
                score = 1.0
            elif any(query_lower in tag.lower() for tag in tool.tags):
                score = 0.8

            if score > 0:
                policy = evaluate_policy(mode, tool.risk_level, tool.tool_id)
                if policy.action == "allow":
                    allowed_in_mode = AllowedInMode.ALLOWED
                elif policy.action == "block":
                    allowed_in_mode = AllowedInMode.BLOCKED
                else:
                    allowed_in_mode = AllowedInMode.REQUIRES_APPROVAL

                results.append(
                    ToolCandidate(
                        tool_id=tool.tool_id,
                        server_id=tool.server_id,
                        description_1line=tool.description_1line,
                        tags=tool.tags,
                        risk_level=tool.risk_level,
                        relevance_score=score,
                        allowed_in_mode=allowed_in_mode,
                        schema_hint=extract_schema_hint(tool.schema_min),
                    )
                )

        # Sort by relevance score (highest first)
        results.sort(key=lambda c: c.relevance_score, reverse=True)

        # Return top 8 results
        return results[:8]

    def get_bootstrap_tools(self) -> set:
        """
        Get set of bootstrap tool IDs.

        Bootstrap tools are:
        - search_tools: Entry point for discovery
        - get_tool_schema: Triggers tool exposure

        These tools are auto-exposed at startup and always available.

        Returns:
            Set of 2 bootstrap tool names
        """
        return self._bootstrap_tools

    def get_all_summaries(self) -> list[ToolRecord]:
        """
        Get all registered tool records.

        Returns:
            List of all ToolRecord objects
        """
        return list(self._tools.values())


# Singleton instance with absolute path
_default_tools_path = os.getenv("TOOLS_YAML_PATH") or str(
    Path(__file__).parent.parent.parent / "config" / "tools.yaml"
)
tool_registry = ToolRegistry.from_yaml(_default_tools_path)
