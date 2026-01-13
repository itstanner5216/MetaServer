"""Runtime context helpers for tool invocation."""

from dataclasses import dataclass
from typing import Optional

from fastmcp import Context

from .leases import ToolLease


@dataclass(frozen=True)
class RunContext:
    """Carries run/session metadata for tool invocations."""

    run_id: Optional[str]
    agent_id: Optional[str]
    session_id: Optional[str]
    lease: Optional[ToolLease] = None


def build_run_context(ctx: Context, lease: Optional[ToolLease] = None) -> RunContext:
    """Build a RunContext from the FastMCP Context."""
    request_context = getattr(ctx, "request_context", None)

    run_id = getattr(request_context, "run_id", None) or getattr(ctx, "run_id", None)
    agent_id = getattr(request_context, "agent_id", None) or getattr(
        ctx, "agent_id", None
    )

    session_value = getattr(ctx, "session_id", None)
    session_id = str(session_value) if session_value is not None else None

    return RunContext(
        run_id=run_id,
        agent_id=agent_id,
        session_id=session_id,
        lease=lease,
    )
