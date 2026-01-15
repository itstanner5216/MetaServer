# context_pack/builder.py
"""
Phase 5: ContextPack Builder for RAG System.

Creates signed, tamper-evident context bundles for the generator.
Uses HMAC-SHA256 over canonical JSON serialization for verification.
"""

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Token Counting Utilities
# -----------------------------------------------------------------------------


def _count_tokens(text: str) -> int:
    """
    Count tokens in text using tiktoken if available, otherwise approximate.

    Uses cl100k_base encoding (GPT-4, Claude compatible).
    Falls back to word-based approximation if tiktoken unavailable.

    Args:
        text: Text to count tokens for

    Returns:
        Estimated token count
    """
    try:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except ImportError:
        # Rough approximation: ~1.3 tokens per word
        return int(len(text.split()) * 1.3)


# -----------------------------------------------------------------------------
# Data Types
# -----------------------------------------------------------------------------


@dataclass
class ContextPack:
    """
    Signed, tamper-evident context bundle for the generator.

    Contains all retrieval and selection context needed for generation,
    along with an HMAC-SHA256 signature for integrity verification.

    The pack is immutable once created - any modification will invalidate
    the signature. Validators can verify authenticity by recomputing
    the signature from pack contents.

    Fields:
        pack_id: Unique UUID for this context pack
        query: Original user query
        query_rewritten: Optional rewritten query (for query expansion)
        lease_id: Lease governing access permissions
        scope: User's permitted scope for this query
        embedding_config: Configuration for embedding model
        retrieval_config: Configuration for retrieval (filters, hybrid, rerank)
        candidates_raw: All retrieved candidates with scores
        candidates_selected: Candidates selected by explainer
        selected_chunk_full_text: Mapping of chunk_id to full text content
        explainer_output: ExplainerOutput as dictionary
        token_budget: Token budget breakdown
        signature: HMAC-SHA256 hex digest
        created_at: When pack was created
        expires_at: When pack expires (TTL enforcement)
    """

    pack_id: str
    query: str
    query_rewritten: str | None
    lease_id: str
    scope: str
    embedding_config: dict[str, Any]
    retrieval_config: dict[str, Any]
    candidates_raw: list[dict[str, Any]]
    candidates_selected: list[dict[str, Any]]
    selected_chunk_full_text: dict[str, str]
    explainer_output: dict[str, Any]
    token_budget: dict[str, int]
    signature: str
    created_at: datetime
    expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """
        Convert pack to dictionary for serialization.

        Returns:
            Dictionary representation of the pack
        """
        return {
            "pack_id": self.pack_id,
            "query": self.query,
            "query_rewritten": self.query_rewritten,
            "lease_id": self.lease_id,
            "scope": self.scope,
            "embedding_config": self.embedding_config,
            "retrieval_config": self.retrieval_config,
            "candidates_raw": self.candidates_raw,
            "candidates_selected": self.candidates_selected,
            "selected_chunk_full_text": self.selected_chunk_full_text,
            "explainer_output": self.explainer_output,
            "token_budget": self.token_budget,
            "signature": self.signature,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPack":
        """
        Create ContextPack from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            ContextPack instance
        """
        return cls(
            pack_id=data["pack_id"],
            query=data["query"],
            query_rewritten=data.get("query_rewritten"),
            lease_id=data["lease_id"],
            scope=data["scope"],
            embedding_config=data["embedding_config"],
            retrieval_config=data["retrieval_config"],
            candidates_raw=data["candidates_raw"],
            candidates_selected=data["candidates_selected"],
            selected_chunk_full_text=data["selected_chunk_full_text"],
            explainer_output=data["explainer_output"],
            token_budget=data["token_budget"],
            signature=data["signature"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    @property
    def is_expired(self) -> bool:
        """Check if the pack has expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def selected_count(self) -> int:
        """Number of selected chunks."""
        return len(self.candidates_selected)

    @property
    def raw_count(self) -> int:
        """Number of raw candidates."""
        return len(self.candidates_raw)

    @property
    def available_tokens(self) -> int:
        """Tokens available for generation."""
        return self.token_budget.get("available_for_generation", 0)


# -----------------------------------------------------------------------------
# ContextPack Builder
# -----------------------------------------------------------------------------


class ContextPackBuilder:
    """
    Builds signed, tamper-evident ContextPacks.

    Uses HMAC-SHA256 over canonical JSON serialization (RFC 8785 style)
    to create verifiable context bundles. The signature covers all
    pack contents except the signature field itself.

    Example:
        builder = ContextPackBuilder(
            hmac_secret="your-secret-key",
            default_ttl_seconds=300,
            token_budget=8000
        )

        pack = builder.build(
            query="How to read files?",
            lease_id="lease-123",
            scope="read:files",
            candidates_raw=raw_candidates,
            selected_chunks=selected,
            explainer_output=explainer_result.to_dict(),
            chunk_texts={"chunk-1": "Full text..."},
            embedding_config={"model": "gemini", "version": "1.0", "topN": 30},
            retrieval_config={"hybrid": True, "rerank": True}
        )

        # Pack is now signed and ready for generator
        assert pack.signature is not None
    """

    def __init__(
        self,
        hmac_secret: str,
        default_ttl_seconds: int = 300,
        token_budget: int = 8000,
    ):
        """
        Initialize the ContextPack builder.

        Args:
            hmac_secret: Secret key for HMAC-SHA256 signing
            default_ttl_seconds: Default time-to-live in seconds (default 5 minutes)
            token_budget: Total token budget for generation (default 8000)

        Raises:
            ValueError: If hmac_secret is empty
        """
        if not hmac_secret:
            raise ValueError("hmac_secret cannot be empty")

        self._hmac_secret = hmac_secret
        self._default_ttl_seconds = default_ttl_seconds
        self._token_budget = token_budget

        # Metrics
        self._packs_created = 0
        self._total_tokens_budgeted = 0

        logger.info(
            f"ContextPackBuilder initialized: ttl={default_ttl_seconds}s, "
            f"token_budget={token_budget}"
        )

    def build(
        self,
        query: str,
        lease_id: str,
        scope: str,
        candidates_raw: list[dict[str, Any]],
        selected_chunks: list[dict[str, Any]],
        explainer_output: dict[str, Any],
        chunk_texts: dict[str, str],
        embedding_config: dict[str, Any],
        retrieval_config: dict[str, Any],
        query_rewritten: str | None = None,
        ttl_seconds: int | None = None,
    ) -> ContextPack:
        """
        Build a signed ContextPack with all retrieval context.

        Args:
            query: Original user query
            lease_id: Lease ID governing access
            scope: User's permitted scope
            candidates_raw: All retrieved candidates with scores
            selected_chunks: Candidates selected by explainer
            explainer_output: ExplainerOutput as dictionary
            chunk_texts: Mapping of chunk_id to full text content
            embedding_config: Embedding configuration dict
            retrieval_config: Retrieval configuration dict
            query_rewritten: Optional rewritten query for expansion
            ttl_seconds: Optional custom TTL (defaults to default_ttl_seconds)

        Returns:
            Signed ContextPack ready for generator

        Raises:
            ValueError: If required parameters are missing
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not lease_id:
            raise ValueError("lease_id cannot be empty")
        if not scope:
            raise ValueError("scope cannot be empty")

        # Generate pack ID and timestamps
        pack_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        expires_at = created_at + timedelta(seconds=ttl)

        # Compute token budget
        token_budget = self._compute_token_budget(chunk_texts)

        logger.info(
            f"Building ContextPack: pack_id={pack_id}, "
            f"query='{query[:50]}...', "
            f"raw_candidates={len(candidates_raw)}, "
            f"selected={len(selected_chunks)}, "
            f"ttl={ttl}s"
        )

        # Build pack data (without signature)
        pack_data = {
            "pack_id": pack_id,
            "query": query.strip(),
            "query_rewritten": query_rewritten.strip() if query_rewritten else None,
            "lease_id": lease_id,
            "scope": scope,
            "embedding_config": embedding_config,
            "retrieval_config": retrieval_config,
            "candidates_raw": candidates_raw,
            "candidates_selected": selected_chunks,
            "selected_chunk_full_text": chunk_texts,
            "explainer_output": explainer_output,
            "token_budget": token_budget,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        # Create canonical representation and sign
        canonical = self._canonicalize(pack_data)
        signature = self._sign(canonical)

        # Create the pack
        pack = ContextPack(
            pack_id=pack_id,
            query=query.strip(),
            query_rewritten=query_rewritten.strip() if query_rewritten else None,
            lease_id=lease_id,
            scope=scope,
            embedding_config=embedding_config,
            retrieval_config=retrieval_config,
            candidates_raw=candidates_raw,
            candidates_selected=selected_chunks,
            selected_chunk_full_text=chunk_texts,
            explainer_output=explainer_output,
            token_budget=token_budget,
            signature=signature,
            created_at=created_at,
            expires_at=expires_at,
        )

        # Update metrics
        self._packs_created += 1
        self._total_tokens_budgeted += token_budget["total_budget"]

        logger.info(
            f"ContextPack created: pack_id={pack_id}, "
            f"signature={signature[:16]}..., "
            f"tokens_available={token_budget['available_for_generation']}"
        )

        return pack

    def _canonicalize(self, pack_data: dict[str, Any]) -> str:
        """
        Create RFC 8785-style canonical JSON serialization.

        Produces deterministic JSON output by:
        - Sorting object keys alphabetically (recursive)
        - No insignificant whitespace
        - Consistent number formatting
        - UTF-8 encoding

        Args:
            pack_data: Dictionary to canonicalize

        Returns:
            Canonical JSON string
        """
        return json.dumps(
            pack_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,  # Handle datetime and other non-JSON types
        )

    def _sign(self, canonical_data: str) -> str:
        """
        Create HMAC-SHA256 signature of canonical data.

        Args:
            canonical_data: Canonical JSON string to sign

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        signature = hmac.new(
            self._hmac_secret.encode("utf-8"),
            canonical_data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _compute_token_budget(
        self,
        selected_texts: dict[str, str],
    ) -> dict[str, int]:
        """
        Compute token budget breakdown for selected chunks.

        Estimates tokens used by selected chunk texts and calculates
        remaining budget available for generation.

        Args:
            selected_texts: Mapping of chunk_id to full text

        Returns:
            Dict with total_budget, used_by_selection, available_for_generation
        """
        # Count tokens in all selected texts
        used_by_selection = sum(_count_tokens(text) for text in selected_texts.values())

        # Calculate available for generation
        available = max(0, self._token_budget - used_by_selection)

        return {
            "total_budget": self._token_budget,
            "used_by_selection": used_by_selection,
            "available_for_generation": available,
        }

    def get_metrics(self) -> dict[str, Any]:
        """
        Get builder metrics.

        Returns:
            Dict with builder statistics
        """
        return {
            "packs_created": self._packs_created,
            "total_tokens_budgeted": self._total_tokens_budgeted,
            "default_ttl_seconds": self._default_ttl_seconds,
            "token_budget": self._token_budget,
        }


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


def create_builder(
    hmac_secret: str,
    default_ttl_seconds: int = 300,
    token_budget: int = 8000,
) -> ContextPackBuilder:
    """
    Create a ContextPackBuilder with the given configuration.

    Args:
        hmac_secret: Secret key for HMAC-SHA256 signing
        default_ttl_seconds: Default TTL in seconds
        token_budget: Total token budget

    Returns:
        Configured ContextPackBuilder instance
    """
    return ContextPackBuilder(
        hmac_secret=hmac_secret,
        default_ttl_seconds=default_ttl_seconds,
        token_budget=token_budget,
    )
