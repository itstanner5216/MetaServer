"""
Discovery utilities and legacy registry for backward compatibility.

Module Status:
- format_search_results(): ACTIVE - Formats search results for agent consumption
- ToolRegistry: DEPRECATED - Use registry.registry.ToolRegistry instead
- ToolSummary: DEPRECATED - Use ToolRecord/ToolCandidate from registry instead
- tool_registry instance: DEPRECATED - Use registry.tool_registry instead

Active Components:
- format_search_results(results) -> str
  Formats tool search results for display to agents. Used by supervisor.py.
  Accepts both legacy ToolSummary and new ToolCandidate objects.

Deprecated Components (kept for backward compatibility):
- ToolRegistry class (replaced by registry/registry.py with config/tools.yaml)
- ToolSummary dataclass (replaced by ToolRecord/ToolCandidate)
- tool_registry singleton (replaced by registry.tool_registry)

Migration Path:
- Prefer registry-backed tools: from meta_mcp.registry import tool_registry
- Legacy fallback (manual registration): from meta_mcp.discovery import tool_registry
  then call register_core_tools() explicitly, or set
  META_MCP_AUTO_REGISTER_DISCOVERY_TOOLS=true to restore legacy auto-registration.
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class ToolSummary:
    """
    Minimal tool metadata for discovery.

    Contains only essential information to minimize context injection.
    """

    name: str
    description: str  # First sentence only
    category: str  # "core", "git", "search", etc.
    sensitive: bool  # True if tool requires governance


class ToolRegistry:
    """
    Tool registry for lazy-loading discovery.

    Features:
    - Minimal bootstrap set (3 tools)
    - Simple string matching for search
    - Metadata-only results (no schemas)
    - Sensitivity classification
    """

    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: dict[str, ToolSummary] = {}

    def register(
        self,
        name: str,
        description: str,
        category: str,
        sensitive: bool = False,
    ):
        """
        Register a tool in the discovery registry.

        IMPORTANT: This does NOT expose the tool to tools/list.
        Tools registered here are:
        - Searchable via search_tools()
        - NOT visible in tools/list until get_tool_schema() is called

        This enables progressive discovery:
        1. Tools are registered at startup (searchable metadata)
        2. Tools remain hidden from tools/list initially
        3. Model uses search_tools() to find relevant tools
        4. Model calls get_tool_schema() to expose and get full schema
        5. Tool then appears in tools/list and can be invoked

        Args:
            name: Tool name (canonical)
            description: First sentence description only
            category: Tool category
            sensitive: Whether tool requires governance (write/execute operations)
        """
        # Extract first sentence if multiple sentences provided
        first_sentence = description.split(".")[0].strip() + "."

        self._tools[name] = ToolSummary(
            name=name,
            description=first_sentence,
            category=category,
            sensitive=sensitive,
        )

    def search(self, query: str) -> List[ToolSummary]:
        """
        Search for tools by name or description.

        Uses simple string matching: name match > description match.
        No ranking, recommendation, or prioritization beyond basic matching.

        Args:
            query: Search query string

        Returns:
            List of matching ToolSummary objects (name matches first, then description matches)
        """
        if not query or not query.strip():
            return []

        query_lower = query.lower().strip()
        name_matches = []
        description_matches = []

        for tool in self._tools.values():
            # Name match takes priority
            if query_lower in tool.name.lower():
                name_matches.append(tool)
            # Description match is secondary
            elif query_lower in tool.description.lower():
                description_matches.append(tool)

        # Return name matches first, then description matches
        return name_matches + description_matches

    def get_bootstrap_tools(self) -> List[str]:
        """
        Get minimal bootstrap tool set for progressive discovery.

        ONLY these tools are exposed at startup:
        - search_tools: Entry point for discovery
        - get_tool_schema: Triggers tool exposure (progressive discovery)

        All other tools (including read_file, list_directory) are:
        1. Registered in this registry (searchable via search_tools)
        2. NOT exposed in tools/list initially
        3. Exposed ONLY when get_tool_schema is called

        This implements true progressive discovery.

        Returns:
            List of 2 bootstrap tool names
        """
        return ["search_tools", "get_tool_schema"]

    def get_all_summaries(self) -> List[ToolSummary]:
        """
        Get all registered tool summaries.

        Returns:
            List of all ToolSummary objects
        """
        return list(self._tools.values())

    def is_registered(self, name: str) -> bool:
        """
        Check if tool is registered.

        Args:
            name: Tool name to check

        Returns:
            True if tool is registered, False otherwise
        """
        return name in self._tools


def register_core_tools():
    """
    Register all core tools with correct sensitivity flags.

    Sensitivity classification:
    - NOT sensitive: read_file, list_directory (read operations)
    - SENSITIVE: write_file, delete_file, create_directory, move_file, execute_command
    """
    # Read operations (NOT sensitive)
    tool_registry.register(
        name="read_file",
        description="Read file contents from workspace.",
        category="core",
        sensitive=False,
    )

    tool_registry.register(
        name="list_directory",
        description="List directory contents with type indicators.",
        category="core",
        sensitive=False,
    )

    # Write operations (SENSITIVE)
    tool_registry.register(
        name="write_file",
        description="Write content to file in workspace.",
        category="core",
        sensitive=True,
    )

    tool_registry.register(
        name="delete_file",
        description="Delete file from workspace.",
        category="core",
        sensitive=True,
    )

    tool_registry.register(
        name="create_directory",
        description="Create directory in workspace.",
        category="core",
        sensitive=True,
    )

    tool_registry.register(
        name="move_file",
        description="Move or rename file within workspace.",
        category="core",
        sensitive=True,
    )

    # Command execution (SENSITIVE)
    tool_registry.register(
        name="execute_command",
        description="Execute shell command with timeout.",
        category="core",
        sensitive=True,
    )

    # Discovery tools (NOT sensitive - required for bootstrap)
    tool_registry.register(
        name="search_tools",
        description="Search for available tools by name or description.",
        category="core",
        sensitive=False,
    )

    tool_registry.register(
        name="get_tool_schema",
        description="Get JSON schema for a specific tool.",
        category="core",
        sensitive=False,
    )

    # Git operations (SENSITIVE)
    tool_registry.register(
        name="git_commit",
        description="Create a git commit with staged changes.",
        category="git",
        sensitive=True,
    )

    tool_registry.register(
        name="git_push",
        description="Push commits to remote repository.",
        category="git",
        sensitive=True,
    )

    tool_registry.register(
        name="git_reset",
        description="Reset git repository to a specific state.",
        category="git",
        sensitive=True,
    )

    # Admin operations (SENSITIVE)
    tool_registry.register(
        name="set_governance_mode",
        description="Set the governance execution mode.",
        category="admin",
        sensitive=True,
    )

    tool_registry.register(
        name="get_governance_status",
        description="Get current governance mode and state.",
        category="admin",
        sensitive=False,
    )

    tool_registry.register(
        name="revoke_all_elevations",
        description="Revoke all active governance elevations.",
        category="admin",
        sensitive=True,
    )


def format_search_results(results) -> str:
    """
    Format search results for agent consumption.

    ACTIVE UTILITY: This function is NOT deprecated and is actively used by supervisor.py.

    Returns ONLY:
    - Tool name
    - One-sentence description
    - Sensitivity flag

    Does NOT include:
    - Arguments or schemas
    - Examples or usage hints
    - Recommendations or rankings

    Args:
        results: List of ToolSummary or ToolCandidate objects

    Returns:
        Formatted string with minimal metadata

    Note:
        Accepts both legacy ToolSummary and new ToolCandidate objects
        for backward compatibility during migration.
    """
    if not results:
        return "No tools found matching your query."

    lines = [f"Found {len(results)} tool(s):\n"]

    for tool in results:
        # Handle both ToolSummary (old) and ToolCandidate (new)
        if hasattr(tool, 'sensitive'):
            # Old ToolSummary
            sensitivity = "[SENSITIVE]" if tool.sensitive else "[SAFE]"
            tool_name = tool.name
            description = tool.description
        else:
            # New ToolCandidate
            sensitivity = "[SAFE]" if tool.risk_level == "safe" else "[SENSITIVE]"
            tool_name = tool.tool_id
            description = tool.description_1line

        lines.append(f"• {tool_name} {sensitivity}")
        lines.append(f"  {description}")
        lines.append("")  # Blank line between tools

    return "\n".join(lines).strip()


# ============================================================================
# DEPRECATED REGISTRY INSTANCE
# ============================================================================
# WARNING: This module-level singleton is DEPRECATED.
# DO NOT use this registry in new code.
#
# Migration:
#   OLD: from meta_mcp.discovery import tool_registry
#   NEW: from meta_mcp.registry import tool_registry
#
# The NEW registry:
# - Loads from config/tools.yaml (static definitions)
# - Uses ToolRecord/ToolCandidate models (richer metadata)
# - Supports semantic search (Phase 2)
# - Is the canonical source of truth
#
# This OLD registry:
# - Uses in-memory registration (dynamic)
# - Uses ToolSummary model (minimal metadata)
# - Only supports keyword search
# - Kept for backward compatibility only
# ============================================================================

# Module-level singleton (DEPRECATED - use registry.tool_registry instead)
tool_registry = ToolRegistry()

# Auto-register core tools on import (DEPRECATED, opt-in only)
_AUTO_REGISTER_ENV = "META_MCP_AUTO_REGISTER_DISCOVERY_TOOLS"
if os.getenv(_AUTO_REGISTER_ENV, "").lower() in {"1", "true", "yes", "on"}:
    register_core_tools()
