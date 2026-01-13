"""Phase 4: Governance Engine

Policy-based access control with HMAC-signed capability tokens.
"""

from .approval import (
    ApprovalDecision,
    ApprovalProvider,
    ApprovalRequest,
    ApprovalResponse,
    DBusGUIProvider,
    FastMCPElicitProvider,
    SystemdFallbackProvider,
    get_approval_provider,
)
from .artifacts import (
    ApprovalArtifactGenerator,
    ArtifactGenerationError,
    get_artifact_generator,
)
from .policy import PolicyDecision, evaluate_policy
from .tokens import decode_token, generate_token, verify_token

__all__ = [
    "generate_token",
    "verify_token",
    "decode_token",
    "evaluate_policy",
    "PolicyDecision",
    "ApprovalDecision",
    "ApprovalProvider",
    "ApprovalRequest",
    "ApprovalResponse",
    "DBusGUIProvider",
    "FastMCPElicitProvider",
    "SystemdFallbackProvider",
    "get_approval_provider",
    "ApprovalArtifactGenerator",
    "ArtifactGenerationError",
    "get_artifact_generator",
]
