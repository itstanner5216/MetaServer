"""Embedding services for semantic search."""

from ...config import Config
from .embedder import (
    EmbedderAdapter,
    EmbeddingResult,
    GeminiEmbedderAdapter,
    OpenAICompatibleEmbedderAdapter,
    RateLimiter,
)


def get_embedder() -> EmbedderAdapter:
    """Create an embedder adapter from configuration."""
    if Config.EMBEDDING_PROVIDER == "gemini":
        return GeminiEmbedderAdapter(
            api_key=Config.EMBEDDING_API_KEY,
            model=Config.EMBEDDING_MODEL,
        )
    return OpenAICompatibleEmbedderAdapter(
        base_url=Config.EMBEDDING_BASE_URL,
        api_key=Config.EMBEDDING_API_KEY,
        model=Config.EMBEDDING_MODEL,
    )

__all__ = [
    "EmbedderAdapter",
    "EmbeddingResult",
    "GeminiEmbedderAdapter",
    "OpenAICompatibleEmbedderAdapter",
    "RateLimiter",
    "get_embedder",
]
