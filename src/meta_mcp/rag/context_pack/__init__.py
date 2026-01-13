# context_pack/__init__.py
"""
Phase 5: ContextPack Builder for RAG System.

Signed, tamper-evident context bundles for the generator.

Components:
- ContextPack: Immutable, signed bundle containing all retrieval context
- ContextPackBuilder: Creates signed ContextPacks with HMAC-SHA256
- ContextPackValidator: Validates signatures and expiration

Architecture:
1. Builder receives retrieval results and explainer output
2. Creates canonical JSON representation of all context
3. Signs with HMAC-SHA256 for tamper detection
4. Pack includes TTL for time-scoped reuse

Key Features:
- HMAC-SHA256 signatures over RFC 8785-style canonical JSON
- TTL enforcement (default 5 minutes)
- Token budget tracking
- Complete audit trail of retrieval/selection context
- Immutability - once signed, contents cannot be modified

Security Model:
- Secret key stored in config/environment (never in pack)
- Signature computed over all pack data except signature field
- Validator recomputes signature to verify integrity
- Expiration prevents unbounded reuse of stale context
"""

from .builder import (
    ContextPack,
    ContextPackBuilder,
)
from .validator import (
    ContextPackValidator,
    ValidationResult,
)

__all__ = [
    "ContextPack",
    "ContextPackBuilder",
    "ContextPackValidator",
    "ValidationResult",
]
