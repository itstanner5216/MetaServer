"""Agent hook system for runtime policy enforcement.

This module provides opt-in hooks for agent-style runs that enforce
reliability and obedience at runtime through the existing lease/tool-permission flow.

Key components:
- HookManager: Central orchestrator loaded from config/agents.yaml
- Gates: Policy enforcement (tool allowlist, path fence, budget limits)
- Models: AgentBinding, PolicyViolation, ToolReceipt

Usage:
    # Check if agent mode is active for a request
    if hook_manager.is_agent_mode(agent_id):
        ctx = hook_manager.start_agent_run(agent_id, session_id)

    # Before tool call
    violation, receipt = await hook_manager.run_before_tool_call(
        session_id, tool_name, arguments
    )
    if violation:
        raise ToolError(str(violation))

    # After tool call
    await hook_manager.run_after_tool_result(
        session_id, tool_name, result, receipt
    )
"""

from .gates import (
    DEFAULT_GATES,
    BudgetGate,
    Gate,
    PathFenceGate,
    ToolAllowlistGate,
    budget_gate,
    path_fence_gate,
    tool_allowlist_gate,
)
from .manager import HookManager, hook_manager
from .models import (
    AgentBinding,
    AgentRunContext,
    GateType,
    HookStage,
    PolicyViolation,
    ToolReceipt,
)

__all__ = [
    # Manager
    "HookManager",
    "hook_manager",
    # Models
    "AgentBinding",
    "AgentRunContext",
    "GateType",
    "HookStage",
    "PolicyViolation",
    "ToolReceipt",
    # Gates
    "Gate",
    "ToolAllowlistGate",
    "PathFenceGate",
    "BudgetGate",
    "tool_allowlist_gate",
    "path_fence_gate",
    "budget_gate",
    "DEFAULT_GATES",
]
