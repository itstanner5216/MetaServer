# retrieval/semantic_search.py
"""
Hybrid semantic + lexical retriever with governance-aware ranking.

Main entry point for Phase 3 RAG retrieval system.
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timedelta

from ..embedding import GeminiEmbedderAdapter
from ..storage import QdrantStorageClient
from .bm25 import BM25Index

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Data Types
# -----------------------------------------------------------------------------


@dataclass
class RetrievalCandidate:
    """
    A candidate chunk returned from retrieval.

    Contains scoring information and governance metadata for
    downstream processing and ranking.
    """

    chunk_id: str
    doc_id: str
    path: str
    score: float  # 0-1, combined score after all adjustments
    semantic_score: float  # Raw semantic similarity score
    bm25_score: Optional[float]  # BM25 lexical score (None if BM25 disabled)
    snippet: str  # First 300 chars of text for preview
    scope: str  # Capability scope (e.g., "core_tools", "admin")
    risk_level: str  # "safe", "sensitive", "dangerous"
    allowed_in_mode: str  # "allowed", "blocked", "prompt_required"
    metadata: Dict  # Additional metadata from payload
    rank: int  # Position in final ranking (1-indexed)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "path": self.path,
            "score": self.score,
            "semantic_score": self.semantic_score,
            "bm25_score": self.bm25_score,
            "snippet": self.snippet,
            "scope": self.scope,
            "risk_level": self.risk_level,
            "allowed_in_mode": self.allowed_in_mode,
            "metadata": self.metadata,
            "rank": self.rank,
        }


# -----------------------------------------------------------------------------
# Query Embedding Cache
# -----------------------------------------------------------------------------


class QueryEmbeddingCache:
    """
    Simple TTL cache for query embeddings.

    Caches embeddings for 60 seconds to avoid redundant API calls
    for repeated or similar queries.
    """

    def __init__(self, ttl_seconds: int = 60, max_size: int = 100):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, Tuple[List[float], datetime]] = {}

    def get(self, query: str) -> Optional[List[float]]:
        """Get cached embedding if not expired."""
        if query not in self._cache:
            return None

        embedding, cached_at = self._cache[query]
        if datetime.utcnow() - cached_at > timedelta(seconds=self.ttl_seconds):
            # Expired
            del self._cache[query]
            return None

        return embedding

    def set(self, query: str, embedding: List[float]) -> None:
        """Cache an embedding."""
        # Evict oldest entries if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        self._cache[query] = (embedding, datetime.utcnow())

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()


# -----------------------------------------------------------------------------
# Governance Ranking Multipliers
# -----------------------------------------------------------------------------


# Score multipliers for governance-aware ranking
# Mode -> Risk Level -> Multiplier
GOVERNANCE_MULTIPLIERS = {
    "READ_ONLY": {
        "safe": 1.0,
        "sensitive": 0.1,  # Heavily penalized
        "dangerous": 0.0,  # Blocked (but still returned for visibility)
    },
    "PERMISSION": {
        "safe": 1.0,
        "sensitive": 0.8,  # Slight penalty
        "dangerous": 0.5,  # Moderate penalty
    },
    "BYPASS": {
        "safe": 1.0,
        "sensitive": 1.0,
        "dangerous": 1.0,
    },
}


# Allowed status by mode and risk level
ALLOWED_STATUS = {
    "READ_ONLY": {
        "safe": "allowed",
        "sensitive": "blocked",
        "dangerous": "blocked",
    },
    "PERMISSION": {
        "safe": "allowed",
        "sensitive": "prompt_required",
        "dangerous": "prompt_required",
    },
    "BYPASS": {
        "safe": "allowed",
        "sensitive": "allowed",
        "dangerous": "allowed",
    },
}


# -----------------------------------------------------------------------------
# Semantic Retriever
# -----------------------------------------------------------------------------


class SemanticRetriever:
    """
    Hybrid semantic + lexical retriever with governance-aware ranking.

    Architecture:
    1. Embed query via Gemini
    2. Search Qdrant for semantic matches
    3. Optionally combine with BM25 lexical scores
    4. Apply governance penalties based on mode
    5. Return ranked candidates

    Latency target: 170ms total retrieval time

    Example:
        retriever = SemanticRetriever(
            qdrant_client=qdrant,
            embedder=embedder,
            enable_bm25=True
        )
        results = retriever.search(
            query="How to read files?",
            scope="core_tools",
            mode="PERMISSION"
        )
    """

    def __init__(
        self,
        qdrant_client: QdrantStorageClient,
        embedder: GeminiEmbedderAdapter,
        enable_bm25: bool = True,
        bm25_weight: float = 0.4,
        semantic_weight: float = 0.6,
        cache_ttl_seconds: int = 60,
    ):
        """
        Initialize the semantic retriever.

        Args:
            qdrant_client: Client for Qdrant vector database
            embedder: Gemini embedding adapter
            enable_bm25: Whether to enable BM25 hybrid search
            bm25_weight: Weight for BM25 scores (0-1)
            semantic_weight: Weight for semantic scores (0-1)
            cache_ttl_seconds: TTL for query embedding cache
        """
        self.qdrant_client = qdrant_client
        self.embedder = embedder
        self.enable_bm25 = enable_bm25
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight

        # Validate weights sum to 1.0
        if abs(bm25_weight + semantic_weight - 1.0) > 0.001:
            logger.warning(
                f"BM25 weight ({bm25_weight}) + semantic weight ({semantic_weight}) "
                f"!= 1.0, results may be unexpected"
            )

        # BM25 index (lazy loaded)
        self._bm25_index: Optional[BM25Index] = None
        self._bm25_scope: Optional[str] = None

        # Query embedding cache
        self._query_cache = QueryEmbeddingCache(ttl_seconds=cache_ttl_seconds)

        # Metrics
        self._search_count = 0
        self._total_latency_ms = 0.0
        self._cache_hits = 0

        logger.info(
            f"SemanticRetriever initialized: "
            f"bm25={enable_bm25}, bm25_weight={bm25_weight}, "
            f"semantic_weight={semantic_weight}"
        )

    def search(
        self,
        query: str,
        scope: str,
        top_k: int = 30,
        mode: str = "PERMISSION",
        filters: Optional[Dict] = None,
    ) -> List[RetrievalCandidate]:
        """
        Search for relevant chunks using hybrid semantic + lexical retrieval.

        Args:
            query: User's search query
            scope: Capability scope to search within (enforced at Qdrant level)
            top_k: Maximum number of results to return
            mode: Governance mode for ranking adjustments
            filters: Additional filters for Qdrant search

        Returns:
            List of RetrievalCandidate objects, ranked by adjusted score

        Note:
            If no results are found, returns empty list.
            Never hallucinate chunk IDs - only return actual results.
        """
        start_time = time.perf_counter()

        try:
            # Validate inputs
            if not query or not query.strip():
                logger.warning("Empty query provided to search")
                return []

            if not scope:
                logger.warning("No scope provided to search")
                return []

            query = query.strip()

            # Step 1: Get query embedding (with caching)
            embedding = self._get_query_embedding(query)
            if embedding is None:
                logger.error("Failed to embed query")
                return []

            # Step 2: Semantic search via Qdrant
            semantic_results = self._search_qdrant(
                embedding=embedding,
                scope=scope,
                top_k=top_k * 2,  # Fetch extra for hybrid merge
                filters=filters,
            )

            if not semantic_results:
                logger.info(f"No semantic results for query: {query[:50]}...")
                return []

            # Step 3: BM25 lexical search (if enabled)
            bm25_results = None
            if self.enable_bm25 and semantic_results:
                bm25_results = self._search_bm25(
                    query=query,
                    scope=scope,
                    top_k=top_k * 2,
                )

            # Step 4: Merge hybrid scores
            if bm25_results:
                merged_results = self._merge_hybrid_scores(
                    semantic_results, bm25_results
                )
            else:
                # Semantic only
                merged_results = [
                    {
                        "chunk_id": r["chunk_id"],
                        "score": r["score"],
                        "semantic_score": r["score"],
                        "bm25_score": None,
                        "payload": r["payload"],
                    }
                    for r in semantic_results
                ]

            # Step 5: Apply governance ranking
            candidates = self._apply_governance_ranking(merged_results, mode)

            # Step 6: Sort by final score and limit
            candidates.sort(key=lambda c: c.score, reverse=True)
            candidates = candidates[:top_k]

            # Step 7: Assign ranks
            for i, candidate in enumerate(candidates):
                candidate.rank = i + 1

            # Record metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._search_count += 1
            self._total_latency_ms += latency_ms

            logger.info(
                f"Search completed: query='{query[:30]}...', "
                f"scope={scope}, results={len(candidates)}, "
                f"latency={latency_ms:.1f}ms"
            )

            # Warn if latency exceeds target
            if latency_ms > 170:
                logger.warning(
                    f"Search latency {latency_ms:.1f}ms exceeds 170ms target"
                )

            return candidates

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """
        Get embedding for query, using cache if available.

        Args:
            query: Query text

        Returns:
            Embedding vector or None if failed
        """
        # Check cache first
        cached = self._query_cache.get(query)
        if cached is not None:
            self._cache_hits += 1
            logger.debug(f"Query embedding cache hit: {query[:30]}...")
            return cached

        # Generate new embedding
        try:
            result = self.embedder.embed_query(query)
            embedding = result.vector

            # Cache for reuse
            self._query_cache.set(query, embedding)

            return embedding

        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return None

    def _search_qdrant(
        self,
        embedding: List[float],
        scope: str,
        top_k: int,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Search Qdrant for semantically similar chunks.

        Args:
            embedding: Query embedding vector
            scope: Required scope filter
            top_k: Number of results
            filters: Additional filters

        Returns:
            List of match dicts with chunk_id, score, payload
        """
        try:
            results = self.qdrant_client.search(
                vector=embedding,
                scope=scope,
                top_k=top_k,
                filters=filters,
            )

            return results

        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

    def _search_bm25(
        self,
        query: str,
        scope: str,
        top_k: int,
    ) -> List[Tuple[str, float]]:
        """
        Search BM25 index for lexical matches.

        Lazily builds/rebuilds index if scope changes.

        Args:
            query: Search query
            scope: Current scope
            top_k: Number of results

        Returns:
            List of (chunk_id, score) tuples
        """
        try:
            # Check if we need to rebuild index for different scope
            if self._bm25_index is None or self._bm25_scope != scope:
                self._build_bm25_index(scope)

            if self._bm25_index is None:
                return []

            return self._bm25_index.search(query, top_k=top_k)

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    def _build_bm25_index(self, scope: str) -> None:
        """
        Build BM25 index for chunks in scope.

        Fetches chunk texts from Qdrant and builds index.

        Args:
            scope: Scope to build index for
        """
        try:
            logger.info(f"Building BM25 index for scope: {scope}")

            # Get all chunks for this scope from Qdrant
            # Note: This is a simplified approach. In production,
            # you might want to iterate with pagination.
            # For now, we do a broad search and extract texts.

            # Use a dummy vector to get all chunks in scope
            # This is a workaround - ideally we'd have a scroll/iterate API
            dummy_vector = [0.0] * 768  # Gemini embedding dimension

            results = self.qdrant_client.search(
                vector=dummy_vector,
                scope=scope,
                top_k=10000,  # Get all chunks
                score_threshold=0.0,  # Accept all
            )

            if not results:
                logger.warning(f"No chunks found for scope {scope}")
                self._bm25_index = BM25Index()
                self._bm25_index.build_index([])
                self._bm25_scope = scope
                return

            # Extract texts for BM25
            chunks = []
            for r in results:
                chunk_id = r["chunk_id"]
                payload = r.get("payload", {})
                text = payload.get("text", "")

                if text:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": text,
                    })

            # Build index
            self._bm25_index = BM25Index()
            self._bm25_index.build_index(chunks)
            self._bm25_scope = scope

            logger.info(f"BM25 index built: {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
            self._bm25_index = None

    def _merge_hybrid_scores(
        self,
        semantic_results: List[Dict],
        bm25_results: List[Tuple[str, float]],
    ) -> List[Dict]:
        """
        Combine semantic and BM25 scores using weighted sum.

        Normalizes both score sets to 0-1 range before combining.

        Args:
            semantic_results: Results from Qdrant with scores
            bm25_results: Results from BM25 with scores

        Returns:
            Merged results with combined scores
        """
        # Convert BM25 results to dict for easy lookup
        bm25_scores = dict(bm25_results)

        # Normalize BM25 scores to 0-1
        if bm25_scores:
            max_bm25 = max(bm25_scores.values())
            min_bm25 = min(bm25_scores.values())
            range_bm25 = max_bm25 - min_bm25

            if range_bm25 > 0:
                bm25_scores = {
                    k: (v - min_bm25) / range_bm25
                    for k, v in bm25_scores.items()
                }
            else:
                # All same score, normalize to 0.5
                bm25_scores = {k: 0.5 for k in bm25_scores}

        # Normalize semantic scores (typically already 0-1 from cosine similarity)
        # but let's ensure it
        semantic_dict = {}
        for r in semantic_results:
            chunk_id = r["chunk_id"]
            semantic_dict[chunk_id] = r

        if semantic_dict:
            scores = [r["score"] for r in semantic_results]
            max_sem = max(scores)
            min_sem = min(scores)
            range_sem = max_sem - min_sem

            if range_sem > 0:
                for r in semantic_results:
                    r["normalized_semantic"] = (r["score"] - min_sem) / range_sem
            else:
                for r in semantic_results:
                    r["normalized_semantic"] = 0.5

        # Merge results
        all_chunk_ids = set(semantic_dict.keys()) | set(bm25_scores.keys())
        merged = []

        for chunk_id in all_chunk_ids:
            # Get semantic score and payload
            if chunk_id in semantic_dict:
                semantic_score = semantic_dict[chunk_id].get("normalized_semantic", 0)
                raw_semantic = semantic_dict[chunk_id]["score"]
                payload = semantic_dict[chunk_id].get("payload", {})
            else:
                semantic_score = 0
                raw_semantic = 0
                payload = {}

            # Get BM25 score
            bm25_score = bm25_scores.get(chunk_id, 0)

            # Combined score
            combined_score = (
                self.semantic_weight * semantic_score +
                self.bm25_weight * bm25_score
            )

            merged.append({
                "chunk_id": chunk_id,
                "score": combined_score,
                "semantic_score": raw_semantic,
                "bm25_score": bm25_score if chunk_id in bm25_scores else None,
                "payload": payload,
            })

        return merged

    def _apply_governance_ranking(
        self,
        merged_results: List[Dict],
        mode: str,
    ) -> List[RetrievalCandidate]:
        """
        Apply governance-based score adjustments.

        Adjusts scores based on governance mode and risk level:
        - READ_ONLY: safe=1.0, sensitive=0.1, dangerous=0.0 (blocked)
        - PERMISSION: safe=1.0, sensitive=0.8, dangerous=0.5
        - BYPASS: all=1.0

        Args:
            merged_results: Results with hybrid scores
            mode: Current governance mode

        Returns:
            List of RetrievalCandidate objects with adjusted scores
        """
        # Get multipliers for this mode
        multipliers = GOVERNANCE_MULTIPLIERS.get(mode, GOVERNANCE_MULTIPLIERS["PERMISSION"])
        status_map = ALLOWED_STATUS.get(mode, ALLOWED_STATUS["PERMISSION"])

        candidates = []

        for result in merged_results:
            payload = result.get("payload", {})

            # Extract metadata
            chunk_id = result["chunk_id"]
            doc_id = payload.get("doc_id", "")
            path = payload.get("path", "")
            text = payload.get("text", "")
            scope = payload.get("scope", "")
            risk_level = payload.get("risk_level", "safe")

            # Ensure valid risk level
            if risk_level not in multipliers:
                risk_level = "safe"

            # Apply governance multiplier
            multiplier = multipliers[risk_level]
            adjusted_score = result["score"] * multiplier

            # Determine allowed status
            allowed_in_mode = status_map.get(risk_level, "allowed")

            # Create snippet (first 300 chars)
            snippet = text[:300] if text else ""

            # Build metadata dict (exclude known fields)
            metadata = {
                k: v for k, v in payload.items()
                if k not in {"doc_id", "path", "text", "scope", "risk_level"}
            }

            candidate = RetrievalCandidate(
                chunk_id=chunk_id,
                doc_id=doc_id,
                path=path,
                score=adjusted_score,
                semantic_score=result["semantic_score"],
                bm25_score=result.get("bm25_score"),
                snippet=snippet,
                scope=scope,
                risk_level=risk_level,
                allowed_in_mode=allowed_in_mode,
                metadata=metadata,
                rank=0,  # Assigned later after sorting
            )

            candidates.append(candidate)

        return candidates

    def invalidate_bm25_cache(self) -> None:
        """Invalidate the BM25 index to force rebuild on next search."""
        self._bm25_index = None
        self._bm25_scope = None
        logger.info("BM25 cache invalidated")

    def clear_query_cache(self) -> None:
        """Clear the query embedding cache."""
        self._query_cache.clear()
        logger.info("Query embedding cache cleared")

    def get_metrics(self) -> Dict:
        """
        Get retrieval metrics.

        Returns:
            Dict with search statistics
        """
        avg_latency = (
            self._total_latency_ms / self._search_count
            if self._search_count > 0
            else 0
        )

        return {
            "search_count": self._search_count,
            "total_latency_ms": self._total_latency_ms,
            "avg_latency_ms": avg_latency,
            "cache_hits": self._cache_hits,
            "bm25_enabled": self.enable_bm25,
            "bm25_weight": self.bm25_weight,
            "semantic_weight": self.semantic_weight,
            "bm25_index_scope": self._bm25_scope,
            "bm25_index_stats": (
                self._bm25_index.get_index_stats()
                if self._bm25_index else None
            ),
        }
