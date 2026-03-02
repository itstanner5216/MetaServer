# embedding/embedder.py
"""
Provider-agnostic embedding adapters with batching, retry, and rate limiting.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import Lock

import httpx

try:
    import google.generativeai as genai  # type: ignore[import-untyped]

    _HAS_GENAI = True
except ImportError:
    _HAS_GENAI = False

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    vector: list[float]
    token_count: int
    model: str
    model_version: str


class EmbedderAdapter(ABC):
    """Abstract base class for embedding adapters."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of texts."""

    @abstractmethod
    def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query."""

    @abstractmethod
    def get_usage(self) -> dict:
        """Return usage metrics for adapter calls."""


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.interval = 60.0 / calls_per_minute
        self.last_call = 0.0
        self.lock = Lock()

    def wait(self):
        """Wait until we can make the next call."""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_call
            if time_since_last < self.interval:
                sleep_time = self.interval - time_since_last
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
            self.last_call = time.time()


class OpenAICompatibleEmbedderAdapter(EmbedderAdapter):
    """Adapter for OpenAI-compatible `/v1/embeddings` APIs."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
        model_version: str = "1.0",
        batch_size: int = 100,
        max_retries: int = 3,
        retry_base_delay: int = 5,
        calls_per_minute: int = 60,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.model_version = model_version
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.timeout = timeout

        self.rate_limiter = RateLimiter(calls_per_minute)
        self.call_count = 0
        self.token_count = 0
        self.error_count = 0

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Batch embed texts with retry handling."""
        results: list[EmbeddingResult] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            results.extend(self._embed_with_retry(batch))
        return results

    def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
        retry_count = 0
        last_error: Exception = RuntimeError("No embedding attempts made")

        while retry_count < self.max_retries:
            try:
                self.rate_limiter.wait()
                payload = {
                    "model": self.model,
                    "input": texts,
                }
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = httpx.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

                embeddings_data = data.get("data", [])
                if not embeddings_data:
                    raise RuntimeError("No embeddings returned from provider")

                results = []
                for text, item in zip(texts, embeddings_data):
                    vector = item.get("embedding", [])
                    results.append(
                        EmbeddingResult(
                            vector=vector,
                            token_count=len(text.split()),
                            model=self.model,
                            model_version=self.model_version,
                        )
                    )

                self.call_count += 1
                self.token_count += sum(len(t.split()) for t in texts)
                return results

            except Exception as e:
                last_error = e
                self.error_count += 1
                wait_time = self.retry_base_delay * (2**retry_count)
                logger.warning(f"Embedding error: {e}. Retrying in {wait_time}s")
                time.sleep(wait_time)
                retry_count += 1

        raise last_error

    def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query for retrieval."""
        return self.embed_batch([query])[0]

    def get_usage(self) -> dict:
        """Get usage statistics."""
        return {
            "call_count": self.call_count,
            "token_count": self.token_count,
            "error_count": self.error_count,
            "model": self.model,
            "model_version": self.model_version,
            "base_url": self.base_url,
        }


class GeminiEmbedderAdapter(EmbedderAdapter):
    """Gemini embedding adapter implementation."""

    def __init__(
        self,
        api_key: str,
        model: str = "models/embedding-001",
        model_version: str = "1.0",
        batch_size: int = 100,
        max_retries: int = 3,
        retry_base_delay: int = 60,
        calls_per_minute: int = 60,
    ):
        if not _HAS_GENAI:
            raise RuntimeError(
                "google-generativeai is required for GeminiEmbedderAdapter. "
                "Install it with: pip install google-generativeai"
            )
        genai.configure(api_key=api_key)
        self.model = model
        self.model_version = model_version
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

        self.rate_limiter = RateLimiter(calls_per_minute)
        self.call_count = 0
        self.token_count = 0
        self.error_count = 0

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Batch embed texts via Gemini API with retry."""
        results = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_results = self._embed_with_retry(batch)
            results.extend(batch_results)

        return results

    def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a single batch with retry logic."""

        retry_count = 0
        last_error: Exception = RuntimeError("No embedding attempts made")

        while retry_count < self.max_retries:
            try:
                self.rate_limiter.wait()
                response = genai.embed_content(
                    model=self.model, content=texts, task_type="retrieval_document"
                )

                self.call_count += 1
                batch_tokens = sum(len(t.split()) for t in texts)
                self.token_count += batch_tokens

                embeddings = response["embedding"]
                if not isinstance(embeddings[0], list):
                    embeddings = [embeddings]

                results = []
                for text, embedding in zip(texts, embeddings):
                    results.append(
                        EmbeddingResult(
                            vector=embedding,
                            token_count=len(text.split()),
                            model=self.model,
                            model_version=self.model_version,
                        )
                    )

                logger.debug(f"Embedded batch of {len(texts)} texts")
                return results

            except Exception as e:
                error_str = str(e)
                last_error = e

                if (
                    "429" in error_str
                    or "quota" in error_str.lower()
                    or "rate" in error_str.lower()
                ):
                    wait_time = self.retry_base_delay * (2**retry_count)
                    logger.warning(
                        f"Rate limit hit, waiting {wait_time}s before retry {retry_count + 1}/{self.max_retries}"
                    )
                    time.sleep(wait_time)
                    retry_count += 1
                    self.error_count += 1
                elif "400" in error_str or "invalid" in error_str.lower():
                    logger.warning(f"Invalid request: {e}")
                    raise
                else:
                    wait_time = 5 * (2**retry_count)
                    logger.warning(f"Embedding error: {e}. Retrying in {wait_time}s")
                    time.sleep(wait_time)
                    retry_count += 1
                    self.error_count += 1

        logger.warning("All retries exhausted for batch embedding")
        raise last_error

    def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query for retrieval."""
        self.rate_limiter.wait()

        try:
            response = genai.embed_content(
                model=self.model, content=query, task_type="retrieval_query"
            )

            self.call_count += 1
            self.token_count += len(query.split())

            return EmbeddingResult(
                vector=response["embedding"],
                token_count=len(query.split()),
                model=self.model,
                model_version=self.model_version,
            )

        except Exception as e:
            self.error_count += 1
            logger.warning(f"Query embedding failed: {e}")
            raise

    def get_usage(self) -> dict:
        """Get usage statistics."""
        return {
            "call_count": self.call_count,
            "token_count": self.token_count,
            "error_count": self.error_count,
            "model": self.model,
            "model_version": self.model_version,
        }

    def reset_usage(self):
        """Reset usage counters (e.g., for daily reset)."""
        self.call_count = 0
        self.token_count = 0
        self.error_count = 0
