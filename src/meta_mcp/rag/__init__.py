"""
MetaMCP+ RAG (Retrieval-Augmented Generation) System

Based on FULL_IMPLEMENTATION_PLAN.md:
- Qdrant vector storage
- Gemini embeddings (768-dim)
- Hybrid semantic + BM25 retrieval
- MCP-compatible lease integration

Architecture:
- storage/: Qdrant client and document management
- retrieval/: Semantic search with governance-aware ranking
- embedding/: Gemini API adapter
- schemas/: Data contracts (ToolRecord, ChunkRecord, etc.)
- explainer/: LLM-based chunk selection with rationales
- context_pack/: Signed, tamper-evident context bundles
"""

__version__ = "0.1.0"
