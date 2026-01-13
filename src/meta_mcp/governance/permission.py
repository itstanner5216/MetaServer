"""Permission request models for governance."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PermissionRequest:
    """Structured permission request for a tool operation.

    Attributes mirror ApprovalRequest with an optional run_context for richer context.
    """

    request_id: str
    tool_name: str
    message: str
    required_scopes: List[str]
    artifacts_path: Optional[str] = None
    timeout_seconds: int = 300
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    run_context: Optional[Any] = None
