"""Gate implementations for agent hook system with auto-discovery."""

import fnmatch
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from loguru import logger

from .models import AgentRunContext, GateType, PolicyViolation


class Gate(ABC):
    """Abstract base class for policy gates."""

    gate_type: GateType

    @abstractmethod
    def check(
        self,
        ctx: AgentRunContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Optional[PolicyViolation]:
        """
        Check if operation passes the gate.

        Args:
            ctx: Agent run context
            tool_name: Name of tool being called
            arguments: Tool arguments

        Returns:
            PolicyViolation if gate blocks, None if gate passes
        """
        pass


class ToolAllowlistGate(Gate):
    """
    Gate that checks if tool is in agent's allowlist.

    Uses AgentBinding.is_tool_allowed() for the check.
    """

    gate_type = GateType.TOOL_ALLOWLIST

    def check(
        self,
        ctx: AgentRunContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Optional[PolicyViolation]:
        """Check if tool is allowed for this agent."""
        if ctx.binding.is_tool_allowed(tool_name):
            return None

        logger.warning(
            f"Tool allowlist gate blocked {tool_name} for agent {ctx.agent_id}"
        )

        return PolicyViolation(
            gate_type=self.gate_type,
            tool_name=tool_name,
            reason=f"Tool '{tool_name}' not allowed for agent '{ctx.agent_id}'",
            details={
                "allowed_tools": ctx.binding.allowed_tools,
                "denied_tools": ctx.binding.denied_tools,
            },
            agent_id=ctx.agent_id,
            session_id=ctx.session_id,
        )


class PathFenceGate(Gate):
    """
    Gate that enforces path-based access control for file operations.

    AUTO-DISCOVERS file tools from the tool registry by checking for
    'filesystem:*' scopes. Stays in sync with tools.yaml automatically.

    Checks file paths against allowed/denied path patterns.
    Supports glob patterns (*, **, ?) via fnmatch.
    """

    gate_type = GateType.PATH_FENCE

    def __init__(self):
        """Initialize with empty cache for auto-discovered tools."""
        self._file_tools_cache: Optional[dict[str, list[str]]] = None

    def _get_file_tools(self) -> dict[str, list[str]]:
        """
        Dynamically discover file tools from the tool registry.

        Discovers any tool with 'filesystem:*' scopes and determines
        which arguments represent file paths based on tool naming patterns.

        Returns:
            Dict mapping tool names to list of path argument names
        """
        if self._file_tools_cache is not None:
            return self._file_tools_cache

        # Import here to avoid circular dependencies at module load time
        try:
            from ..registry import tool_registry
        except ImportError:
            logger.warning("Could not import tool_registry, using fallback file tools")
            # Fallback to basic set
            self._file_tools_cache = {
                "read_file": ["path"],
                "write_file": ["path"],
                "delete_file": ["path"],
                "move_file": ["source", "destination"],
                "create_directory": ["path"],
                "remove_directory": ["path"],
                "list_directory": ["path"],
            }
            return self._file_tools_cache

        file_tools = {}

        try:
            # Get all registered tools
            all_tools = tool_registry.get_all_summaries()

            for tool_record in all_tools:
                # Check if tool has filesystem scopes
                has_filesystem_scope = any(
                    scope.startswith('filesystem:')
                    for scope in tool_record.required_scopes
                )

                if not has_filesystem_scope:
                    continue

                tool_id = tool_record.tool_id

                # Determine path argument names based on tool name patterns
                if 'move' in tool_id or 'rename' in tool_id:
                    # Move/rename operations typically have source and destination
                    file_tools[tool_id] = ['source', 'destination']
                elif 'copy' in tool_id:
                    # Copy operations also have source and destination
                    file_tools[tool_id] = ['source', 'destination']
                else:
                    # Most file tools use 'path' argument
                    file_tools[tool_id] = ['path']

            logger.info(
                f"PathFenceGate auto-discovered {len(file_tools)} file tools from registry"
            )

        except Exception as e:
            logger.error(f"Failed to auto-discover file tools: {e}, using fallback")
            file_tools = {
                "read_file": ["path"],
                "write_file": ["path"],
                "delete_file": ["path"],
                "move_file": ["source", "destination"],
                "create_directory": ["path"],
                "remove_directory": ["path"],
                "list_directory": ["path"],
            }

        # Cache for performance
        self._file_tools_cache = file_tools
        return file_tools

    def _normalize_path(self, path: str) -> str:
        """Normalize path for comparison."""
        # Expand user and vars, normalize slashes
        path = os.path.expanduser(path)
        path = os.path.expandvars(path)
        path = os.path.normpath(path)
        return path

    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches a glob pattern."""
        path = self._normalize_path(path)
        pattern = self._normalize_path(pattern)

        # Handle ** for recursive matching
        if "**" in pattern:
            # Convert ** to work with fnmatch
            # Split pattern at ** and check parts
            parts = pattern.split("**")
            if len(parts) == 2:
                prefix, suffix = parts
                prefix = prefix.rstrip(os.sep)
                suffix = suffix.lstrip(os.sep)
                if prefix and not path.startswith(prefix):
                    return False
                if suffix and not path.endswith(suffix):
                    return False
                if prefix and suffix:
                    middle = path[len(prefix) : -len(suffix) if suffix else None]
                    return True
                return True

        return fnmatch.fnmatch(path, pattern)

    def _is_path_allowed(
        self, path: str, ctx: AgentRunContext
    ) -> tuple[bool, str]:
        """
        Check if path is allowed based on agent binding.

        Priority:
        1. If matches denied_paths -> False
        2. If allowed_paths is empty -> True (all allowed)
        3. If matches allowed_paths -> True
        4. Otherwise -> False
        """
        path = self._normalize_path(path)

        # Check denied paths first
        for pattern in ctx.binding.denied_paths:
            if self._path_matches_pattern(path, pattern):
                return False, f"Path matches denied pattern: {pattern}"

        # If no allowed paths specified, allow all (that aren't denied)
        if not ctx.binding.allowed_paths:
            return True, ""

        # Check if matches any allowed path
        for pattern in ctx.binding.allowed_paths:
            if self._path_matches_pattern(path, pattern):
                return True, ""

        return False, f"Path not in allowed paths: {ctx.binding.allowed_paths}"

    def check(
        self,
        ctx: AgentRunContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Optional[PolicyViolation]:
        """Check if file paths are within allowed fence."""
        # Get dynamically discovered file tools
        file_tools = self._get_file_tools()

        # Skip non-file tools
        if tool_name not in file_tools:
            return None

        # Get path arguments for this tool
        path_args = file_tools[tool_name]
        violations = []

        for arg_name in path_args:
            path = arguments.get(arg_name)
            if not path:
                continue

            is_allowed, reason = self._is_path_allowed(path, ctx)
            if not is_allowed:
                violations.append(f"{arg_name}={path}: {reason}")

        if violations:
            logger.warning(
                f"Path fence gate blocked {tool_name} for agent {ctx.agent_id}: "
                f"{violations}"
            )
            return PolicyViolation(
                gate_type=self.gate_type,
                tool_name=tool_name,
                reason=f"Path access denied: {'; '.join(violations)}",
                details={
                    "violations": violations,
                    "allowed_paths": ctx.binding.allowed_paths,
                    "denied_paths": ctx.binding.denied_paths,
                },
                agent_id=ctx.agent_id,
                session_id=ctx.session_id,
            )

        return None


class BudgetGate(Gate):
    """
    Gate that enforces tool call budget limits.

    Tracks:
    - Global tool call count vs max_tool_calls
    - Per-tool call counts vs max_tool_calls_per_tool
    """

    gate_type = GateType.BUDGET_LIMIT

    def check(
        self,
        ctx: AgentRunContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Optional[PolicyViolation]:
        """Check if tool call is within budget."""
        is_allowed, reason = ctx.is_within_budget(tool_name)

        if is_allowed:
            return None

        logger.warning(
            f"Budget gate blocked {tool_name} for agent {ctx.agent_id}: {reason}"
        )

        return PolicyViolation(
            gate_type=self.gate_type,
            tool_name=tool_name,
            reason=reason,
            details={
                "current_total_calls": ctx.tool_call_count,
                "max_total_calls": ctx.binding.max_tool_calls,
                "current_tool_calls": ctx.tool_call_counts_by_tool.get(tool_name, 0),
                "max_tool_calls": ctx.binding.max_tool_calls_per_tool.get(tool_name),
            },
            agent_id=ctx.agent_id,
            session_id=ctx.session_id,
        )


# Default gate instances for easy import
tool_allowlist_gate = ToolAllowlistGate()
path_fence_gate = PathFenceGate()
budget_gate = BudgetGate()

DEFAULT_GATES: list[Gate] = [
    tool_allowlist_gate,
    path_fence_gate,
    budget_gate,
]
