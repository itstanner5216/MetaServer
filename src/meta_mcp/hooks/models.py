"""Hook system models for agent runtime spine."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class HookStage(str, Enum):
    """Hook execution stages in the tool call lifecycle."""

    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_RESULT = "after_tool_result"
    ON_ERROR = "on_error"


class GateType(str, Enum):
    """Types of policy gates."""

    TOOL_ALLOWLIST = "tool_allowlist"
    PATH_FENCE = "path_fence"
    BUDGET_LIMIT = "budget_limit"
    CUSTOM = "custom"


@dataclass
class PolicyViolation:
    """
    Machine-readable policy violation structure.

    Returned by gates when a policy check fails.
    Provides structured data for agent error handling.
    """

    gate_type: GateType
    tool_name: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "gate_type": self.gate_type.value,
            "tool_name": self.tool_name,
            "reason": self.reason,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
        }

    def __str__(self) -> str:
        return f"PolicyViolation({self.gate_type.value}): {self.reason}"


@dataclass
class AgentBinding:
    """
    Agent-to-model binding configuration.

    Defines which model plays which role and what tools are allowed.
    Loaded from config/agents.yaml.
    """

    agent_id: str
    role_id: str
    model_id: str  # LiteLLM model name/profile
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    max_tool_calls: int = 100
    max_tool_calls_per_tool: dict[str, int] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if tool is allowed for this agent.

        Priority:
        1. If in denied_tools -> False
        2. If allowed_tools is empty -> True (all allowed by default)
        3. If in allowed_tools -> True
        4. Otherwise -> False
        """
        if tool_name in self.denied_tools:
            return False
        if not self.allowed_tools:
            return True
        return tool_name in self.allowed_tools


@dataclass
class ToolReceipt:
    """
    Trace receipt for a tool call execution.

    Provides minimal audit trail without breaking existing logs.
    """

    tool_name: str
    agent_id: str
    session_id: str
    timestamp_start: datetime
    timestamp_end: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    args_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: Optional[str] = None
    duration_ms: Optional[float] = None
    hooks_applied: list[str] = field(default_factory=list)

    def finalize(
        self,
        success: bool,
        error: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> "ToolReceipt":
        """Finalize receipt with execution results."""
        self.timestamp_end = datetime.now(timezone.utc)
        self.success = success
        self.error = error
        self.result_summary = result_summary
        if self.timestamp_end and self.timestamp_start:
            delta = self.timestamp_end - self.timestamp_start
            self.duration_ms = delta.total_seconds() * 1000
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "timestamp_start": self.timestamp_start.isoformat(),
            "timestamp_end": self.timestamp_end.isoformat() if self.timestamp_end else None,
            "success": self.success,
            "error": self.error,
            "args_summary": self.args_summary,
            "result_summary": self.result_summary,
            "duration_ms": self.duration_ms,
            "hooks_applied": self.hooks_applied,
        }


@dataclass
class AgentRunContext:
    """
    Runtime context for an agent execution.

    Tracks state across a single agent run including budget consumption.
    """

    agent_id: str
    session_id: str
    binding: AgentBinding
    tool_call_count: int = 0
    tool_call_counts_by_tool: dict[str, int] = field(default_factory=dict)
    receipts: list[ToolReceipt] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True

    def increment_tool_call(self, tool_name: str) -> None:
        """Increment tool call counters."""
        self.tool_call_count += 1
        self.tool_call_counts_by_tool[tool_name] = (
            self.tool_call_counts_by_tool.get(tool_name, 0) + 1
        )

    def is_within_budget(self, tool_name: str) -> tuple[bool, str]:
        """
        Check if tool call is within budget limits.

        Returns:
            Tuple of (is_allowed, reason_if_denied)
        """
        # Check global limit
        if self.tool_call_count >= self.binding.max_tool_calls:
            return False, f"Global tool call limit reached ({self.binding.max_tool_calls})"

        # Check per-tool limit
        per_tool_limit = self.binding.max_tool_calls_per_tool.get(tool_name)
        if per_tool_limit is not None:
            current_count = self.tool_call_counts_by_tool.get(tool_name, 0)
            if current_count >= per_tool_limit:
                return False, f"Per-tool limit reached for {tool_name} ({per_tool_limit})"

        return True, ""

    def add_receipt(self, receipt: ToolReceipt) -> None:
        """Add a tool receipt to the context."""
        self.receipts.append(receipt)
