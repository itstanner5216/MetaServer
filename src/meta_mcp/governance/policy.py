"""Governance policy engine (Phase 4)."""

from dataclasses import dataclass
from typing import Literal

from ..state import ExecutionMode


@dataclass
class PolicyDecision:
    """
    Policy decision result.

    Contains the action to take and reasoning.

    Design Plan Section 5.4
    """

    action: Literal["allow", "block", "require_approval"]
    requires_approval: bool
    reason: str


def evaluate_policy(
    mode: ExecutionMode,
    tool_risk: str,
    tool_id: str,
) -> PolicyDecision:
    """
    Evaluate governance policy based on mode and tool risk.

    Policy Matrix:
    ┌──────────────┬─────────┬───────────┬───────────┐
    │ Mode         │ Safe    │ Sensitive │ Dangerous │
    ├──────────────┼─────────┼───────────┼───────────┤
    │ READ_ONLY    │ Allow   │ Block     │ Block     │
    │ PERMISSION   │ Allow   │ Approval  │ Approval  │
    │ BYPASS       │ Allow   │ Allow     │ Allow     │
    └──────────────┴─────────┴───────────┴───────────┘

    Args:
        mode: Current governance mode
        tool_risk: Tool risk level ("safe", "sensitive", "dangerous")
        tool_id: Tool identifier

    Returns:
        PolicyDecision with action and reasoning

    Security:
    - Unknown risk levels fail-safe to require_approval
    - Bootstrap tools always allowed
    - Deterministic policy evaluation

    Design Plan Section 5.5
    """
    # Bootstrap tools are always allowed
    if tool_id in {"search_tools", "get_tool_schema"}:
        return PolicyDecision(
            action="allow",
            requires_approval=False,
            reason=f"Bootstrap tool {tool_id} is always allowed",
        )

    # Normalize risk level
    risk = tool_risk.lower() if tool_risk else "unknown"

    # Apply policy matrix
    if mode == ExecutionMode.BYPASS:
        # BYPASS mode: Allow everything
        return PolicyDecision(
            action="allow",
            requires_approval=False,
            reason=f"BYPASS mode allows all tools (risk={risk})",
        )

    elif mode == ExecutionMode.READ_ONLY:
        # READ_ONLY mode: Allow only safe tools
        if risk == "safe":
            return PolicyDecision(
                action="allow",
                requires_approval=False,
                reason="READ_ONLY mode allows safe tools",
            )
        else:
            return PolicyDecision(
                action="block",
                requires_approval=False,
                reason=f"READ_ONLY mode blocks {risk} tools",
            )

    elif mode == ExecutionMode.PERMISSION:
        # PERMISSION mode: Allow safe, require approval for sensitive/dangerous
        if risk == "safe":
            return PolicyDecision(
                action="allow",
                requires_approval=False,
                reason="PERMISSION mode allows safe tools",
            )
        elif risk in {"sensitive", "dangerous"}:
            return PolicyDecision(
                action="require_approval",
                requires_approval=True,
                reason=f"PERMISSION mode requires approval for {risk} tools",
            )
        else:
            # Unknown risk: Fail-safe to require approval
            return PolicyDecision(
                action="require_approval",
                requires_approval=True,
                reason=f"Unknown risk level '{risk}' requires approval (fail-safe)",
            )

    else:
        # Unknown mode: Fail-safe to require approval
        return PolicyDecision(
            action="require_approval",
            requires_approval=True,
            reason=f"Unknown mode '{mode}' requires approval (fail-safe)",
        )
