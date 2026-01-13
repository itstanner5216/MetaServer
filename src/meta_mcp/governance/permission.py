"""Permission request model for governance approval workflows."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PermissionRequest:
    """Structured permission request prior to approval provider dispatch.

    Attributes:
        request_id: Unique identifier for this approval request
        tool_name: Name of the tool requiring approval
        message: Human-readable description of the operation
        required_scopes: List of permission scopes required for this operation
        artifacts_path: Optional path to HTML/JSON artifacts for context
        timeout_seconds: How long to wait for user response
        context_metadata: Additional context (tool args, session info, etc.)
        run_context: Optional runtime context for the current tool execution
    """

    request_id: str
    tool_name: str
    message: str
    required_scopes: List[str]
    artifacts_path: Optional[str] = None
    timeout_seconds: int = 300
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    run_context: Optional[Any] = None
