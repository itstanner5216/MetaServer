# explainer/__init__.py
"""
Phase 4: Retrieval Explainer/Selector for RAG System.

LLM-based chunk selection with human-readable explanations.

Components:
- RetrievalExplainer: Main LLM-based chunk selector
- ExplainerOutput: Structured output with selections and rationales
- create_explainer: Convenience function for creating explainer instances

Architecture:
1. Receive top-30 candidates from retrieval phase
2. Build prompt with query and candidate snippets
3. Use LLM to select 3-12 most relevant chunks
4. Validate selected chunk IDs (hallucination detection)
5. Return structured output with rationales and confidence

Key Features:
- Human-readable rationales for each selection
- Key concept extraction from query and chunks
- Missing context detection for re-retrieval
- Token budget enforcement
- Fallback to score-based selection on LLM failure

Latency: ~500-800ms for LLM call (depending on model)
"""

from .explainer import (
    ExplainerOutput,
    RetrievalExplainer,
    create_explainer,
)

__all__ = [
    "ExplainerOutput",
    "RetrievalExplainer",
    "create_explainer",
]
