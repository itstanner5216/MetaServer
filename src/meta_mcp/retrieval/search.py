"""
Semantic search implementation using cosine similarity.

Provides ranking of tools based on semantic similarity between
query and tool descriptions using embedding vectors.
"""

import asyncio

from ..governance.policy import evaluate_policy
from ..registry.models import AllowedInMode, ToolCandidate, extract_schema_hint
from ..registry.registry import ToolRegistry
from ..state import governance_state
from .embedder import ToolEmbedder


class SemanticSearch:
    """
    Semantic search for tools using embedding-based similarity.

    Features:
    - Lazy index building (only when first search is performed)
    - Cosine similarity ranking
    - Configurable result limits
    - Fallback to keyword search if embeddings fail
    """

    def __init__(self, registry: ToolRegistry):
        """
        Initialize semantic search with a tool registry.

        Args:
            registry: ToolRegistry instance to search
        """
        self.registry = registry
        self.embedder = ToolEmbedder()
        self._index_built = False

    def _build_index(self) -> None:
        """
        Build embedding index from registry.

        Lazy initialization - only called on first search.
        """
        if self._index_built:
            return

        # Get all tools from registry
        tools = self.registry.get_all_summaries()

        if not tools:
            return

        # Build embeddings for all tools
        self.embedder.build_index(tools)

        self._index_built = True

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec_a: First vector
            vec_b: Second vector

        Returns:
            Cosine similarity score in range [0, 1]
        """
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        # Vectors are already normalized, so dot product = cosine similarity
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

        # Clamp to [0, 1] range (handles floating point errors)
        return max(0.0, min(1.0, dot_product))

    def search(self, query: str, limit: int = 10, min_score: float = 0.0) -> list[ToolCandidate]:
        """
        Search tools using semantic similarity.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (0.0 to 1.0)

        Returns:
            List of ToolCandidate objects ranked by relevance
        """
        if not query or not query.strip():
            return []

        # Build index on first search
        self._build_index()

        # Generate query embedding
        query_embedding = self.embedder.embed_query(query)

        # Calculate similarity scores for all tools
        scored_tools = []
        for tool in self.registry.get_all_summaries():
            tool_embedding = self.embedder.get_cached_embedding(tool.tool_id)

            # Skip if embedding failed
            if not tool_embedding or all(x == 0.0 for x in tool_embedding):
                continue

            # Calculate cosine similarity
            score = self._cosine_similarity(query_embedding, tool_embedding)

            # Apply minimum score threshold
            if score >= min_score:
                scored_tools.append((tool, score))

        # Apply governance penalties and annotate policy
        mode = self._resolve_governance_mode()
        adjusted_tools = []
        for tool, score in scored_tools:
            policy = evaluate_policy(mode, tool.risk_level, tool.tool_id)
            if policy.action == "allow":
                penalty = 0.0
                allowed_in_mode = AllowedInMode.ALLOWED
            elif policy.action == "require_approval":
                penalty = 0.20
                allowed_in_mode = AllowedInMode.REQUIRES_APPROVAL
            else:
                penalty = 0.80
                allowed_in_mode = AllowedInMode.BLOCKED

            adjusted_score = score * (1.0 - penalty)
            adjusted_tools.append((tool, adjusted_score, allowed_in_mode))

        # Sort by adjusted score (highest first)
        adjusted_tools.sort(key=lambda x: x[1], reverse=True)

        # Convert to ToolCandidate objects
        results = []
        for tool, score, allowed_in_mode in adjusted_tools[:limit]:
            results.append(
                ToolCandidate(
                    tool_id=tool.tool_id,
                    server_id=tool.server_id,
                    description_1line=tool.description_1line,
                    tags=tool.tags,
                    risk_level=tool.risk_level,
                    relevance_score=score,
                    allowed_in_mode=allowed_in_mode,
                    schema_hint=extract_schema_hint(tool.schema_min),
                )
            )

        return results

    @staticmethod
    def _resolve_governance_mode():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(governance_state.get_mode())
        return governance_state._default_mode()

    def rebuild_index(self) -> None:
        """
        Force rebuild of embedding index.

        Useful if registry contents change.
        """
        self._index_built = False
        self.embedder.clear_cache()
        self._build_index()


def search_tools_semantic(
    registry: ToolRegistry, query: str, limit: int = 10
) -> list[ToolCandidate]:
    """
    Convenience function for semantic search.

    Args:
        registry: ToolRegistry to search
        query: Search query string
        limit: Maximum number of results

    Returns:
        List of ToolCandidate objects ranked by semantic similarity
    """
    searcher = SemanticSearch(registry)
    return searcher.search(query, limit=limit)
