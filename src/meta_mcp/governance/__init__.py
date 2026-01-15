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
    "ApprovalArtifactGenerator",
    "ApprovalDecision",
    "ApprovalProvider",
    "ApprovalRequest",
    "ApprovalResponse",
    "ArtifactGenerationError",
    "DBusGUIProvider",
    "FastMCPElicitProvider",
    "PolicyDecision",
    "SystemdFallbackProvider",
    "decode_token",
    "evaluate_policy",
    "generate_token",
    "get_approval_provider",
    "get_artifact_generator",
    "verify_token",
]
