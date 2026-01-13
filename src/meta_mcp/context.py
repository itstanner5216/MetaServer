"""Context utilities for tool execution and governance."""

from dataclasses import dataclass
from typing import Optional

from .leases.models import ToolLease


@dataclass
class RunContext:
    """
    Structured metadata for a tool invocation.

    Attributes:
        run_id: External run identifier, if provided by the caller.
        lease: Validated and consumed lease information, if available.
        agent_id: Agent identifier from the request context, if provided.
        client_id: Stable client/session identifier.
        tool_name: Name of the tool being invoked.
    """

    run_id: Optional[str]
    lease: Optional[ToolLease]
    agent_id: Optional[str]
    client_id: str
    tool_name: str
