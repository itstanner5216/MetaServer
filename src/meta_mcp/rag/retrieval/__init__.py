# retrieval/__init__.py
"""
Phase 3 Retrieval Service for RAG System.

Implements hybrid semantic + lexical retrieval with governance-aware ranking.

Components:
- SemanticRetriever: Main hybrid retriever (semantic + BM25)
- BM25Index: In-memory BM25 lexical search index
- RetrievalCandidate: Result dataclass with scoring and governance info

Architecture:
1. Embed query via Gemini
2. Search Qdrant for semantic matches
3. Optionally combine with BM25 lexical scores
4. Apply governance penalties based on mode
5. Return ranked candidates

Latency Target: 170ms total retrieval time
"""

from .bm25 import BM25Index
from .semantic_search import RetrievalCandidate, SemanticRetriever

__all__ = [
    "BM25Index",
    "RetrievalCandidate",
    "SemanticRetriever",
]
