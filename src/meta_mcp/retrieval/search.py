"""
Semantic search implementation using cosine similarity.

Provides ranking of tools based on semantic similarity between
query and tool descriptions using embedding vectors.
"""

import asyncio
import heapq
import math

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

    @staticmethod
    def _vector_magnitude(vector: list[float]) -> float:
        return math.sqrt(sum(x * x for x in vector))

    @staticmethod
    def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Returns 0.0 for empty or mismatched vectors.
        """
        if not vector_a or not vector_b or len(vector_a) != len(vector_b):
            return 0.0

        mag_a = SemanticSearch._vector_magnitude(vector_a)
        mag_b = SemanticSearch._vector_magnitude(vector_b)
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0

        dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
        score = dot_product / (mag_a * mag_b)
        return max(0.0, min(1.0, score))

    def _cosine_similarity_with_query(
        self, query_vector: list[float], query_magnitude: float, tool_vector: list[float]
    ) -> float:
        """
        Compute cosine similarity between query and tool vector.

        Args:
            query_vector: Query embedding vector
            query_magnitude: Pre-computed query vector magnitude
            tool_vector: Tool embedding vector

        Returns:
            Cosine similarity score in range [0, 1]
        """
        if (
            not query_vector
            or not tool_vector
            or len(query_vector) != len(tool_vector)
            or query_magnitude == 0.0
        ):
            return 0.0

        # Vectors are already normalized, so dot product = cosine similarity
        dot_product = sum(a * b for a, b in zip(query_vector, tool_vector))
        score = dot_product / query_magnitude

        # Clamp to [0, 1] range (handles floating point errors)
        return max(0.0, min(1.0, score))

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
        query_magnitude = self._vector_magnitude(query_embedding)
        if query_magnitude == 0.0:
            return []

        tools = self.registry.get_all_summaries()
        use_numpy = len(tools) >= 100
        numpy = None
        if use_numpy:
            try:
                import numpy as numpy  # type: ignore[import-not-found]
            except ImportError:
                numpy = None
                use_numpy = False

        mode = self._resolve_governance_mode()
        top_k = max(limit, 0)
        adjusted_tools: list[tuple[float, str, object, AllowedInMode]] = []

        def _push_top_k(tool, score: float, allowed_in_mode: AllowedInMode) -> None:
            if top_k == 0:
                return
            entry = (score, tool.tool_id, tool, allowed_in_mode)
            if len(adjusted_tools) < top_k:
                heapq.heappush(adjusted_tools, entry)
            elif score > adjusted_tools[0][0]:
                heapq.heapreplace(adjusted_tools, entry)

        def _apply_governance(tool, raw_score: float) -> None:
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
            adjusted_score = raw_score * (1.0 - penalty)
            _push_top_k(tool, adjusted_score, allowed_in_mode)

        if use_numpy and numpy is not None:
            tool_vectors = []
            tool_records = []
            for tool in tools:
                tool_embedding = self.embedder.get_cached_embedding(tool.tool_id)
                if not tool_embedding or all(x == 0.0 for x in tool_embedding):
                    continue
                tool_vectors.append(tool_embedding)
                tool_records.append(tool)

            if tool_vectors:
                tool_matrix = numpy.array(tool_vectors, dtype=float)
                query_vector = numpy.array(query_embedding, dtype=float)
                query_magnitude = numpy.linalg.norm(query_vector)
                if query_magnitude == 0.0:
                    return []
                scores = tool_matrix.dot(query_vector) / query_magnitude
                scores = numpy.clip(scores, 0.0, 1.0)
                for tool, score in zip(tool_records, scores.tolist()):
                    if score >= min_score:
                        _apply_governance(tool, score)
        else:
            for tool in tools:
                tool_embedding = self.embedder.get_cached_embedding(tool.tool_id)

                # Skip if embedding failed
                if not tool_embedding or all(x == 0.0 for x in tool_embedding):
                    continue

                score = self._cosine_similarity_with_query(
                    query_embedding, query_magnitude, tool_embedding
                )

                if score >= min_score:
                    _apply_governance(tool, score)

        # Convert to ToolCandidate objects
        results = []
        adjusted_tools.sort(key=lambda x: x[0], reverse=True)
        for score, _tool_id, tool, allowed_in_mode in adjusted_tools[:limit]:
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
        return governance_state.get_cached_mode()

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
