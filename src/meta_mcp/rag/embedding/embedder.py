# embedding/embedder.py
"""
Gemini API embedding adapter with batching, retry, and rate limiting.
"""

import google.generativeai as genai
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    vector: List[float]
    token_count: int
    model: str
    model_version: str


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


class GeminiEmbedderAdapter:
    """
    Adapter for Gemini embedding API with production features.

    Features:
    - Batch embedding (up to 100 texts per call)
    - Automatic retry with exponential backoff
    - Rate limiting
    - Usage tracking for quota management
    """

    def __init__(
        self,
        api_key: str,
        model: str = "models/embedding-001",
        model_version: str = "1.0",
        batch_size: int = 100,
        max_retries: int = 3,
        retry_base_delay: int = 60,
        calls_per_minute: int = 60
    ):
        genai.configure(api_key=api_key)
        self.model = model
        self.model_version = model_version
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

        # Rate limiter
        self.rate_limiter = RateLimiter(calls_per_minute)

        # Usage tracking
        self.call_count = 0
        self.token_count = 0
        self.error_count = 0

    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """
        Batch embed texts via Gemini API with retry.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResult objects
        """
        results = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_results = self._embed_with_retry(batch)
            results.extend(batch_results)

        return results

    def _embed_with_retry(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed a single batch with retry logic."""

        retry_count = 0
        last_error = None

        while retry_count < self.max_retries:
            try:
                # Rate limiting
                self.rate_limiter.wait()

                # Make API call
                response = genai.embed_content(
                    model=self.model,
                    content=texts,
                    task_type="retrieval_document"
                )

                # Track usage
                self.call_count += 1
                batch_tokens = sum(len(t.split()) for t in texts)  # Approximate
                self.token_count += batch_tokens

                # Parse response
                embeddings = response['embedding']

                # Handle single vs batch response
                if not isinstance(embeddings[0], list):
                    embeddings = [embeddings]

                results = []
                for text, embedding in zip(texts, embeddings):
                    results.append(EmbeddingResult(
                        vector=embedding,
                        token_count=len(text.split()),  # Approximate
                        model=self.model,
                        model_version=self.model_version
                    ))

                logger.debug(f"Embedded batch of {len(texts)} texts")
                return results

            except Exception as e:
                error_str = str(e)
                last_error = e

                # Check for rate limit errors
                if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                    wait_time = self.retry_base_delay * (2 ** retry_count)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry {retry_count + 1}/{self.max_retries}")
                    time.sleep(wait_time)
                    retry_count += 1
                    self.error_count += 1
                elif "400" in error_str or "invalid" in error_str.lower():
                    # Bad request - don't retry
                    logger.error(f"Invalid request: {e}")
                    raise
                else:
                    # Other errors - retry with shorter delay
                    wait_time = 5 * (2 ** retry_count)
                    logger.warning(f"Embedding error: {e}. Retrying in {wait_time}s")
                    time.sleep(wait_time)
                    retry_count += 1
                    self.error_count += 1

        # All retries exhausted
        logger.error(f"All retries exhausted for batch embedding")
        raise last_error

    def embed_query(self, query: str) -> EmbeddingResult:
        """
        Embed a single query for retrieval.

        Uses "retrieval_query" task type for asymmetric search.
        """
        self.rate_limiter.wait()

        try:
            response = genai.embed_content(
                model=self.model,
                content=query,
                task_type="retrieval_query"
            )

            self.call_count += 1
            self.token_count += len(query.split())

            return EmbeddingResult(
                vector=response['embedding'],
                token_count=len(query.split()),
                model=self.model,
                model_version=self.model_version
            )

        except Exception as e:
            self.error_count += 1
            logger.error(f"Query embedding failed: {e}")
            raise

    def get_usage(self) -> Dict:
        """Get usage statistics."""
        return {
            "call_count": self.call_count,
            "token_count": self.token_count,
            "error_count": self.error_count,
            "model": self.model,
            "model_version": self.model_version
        }

    def reset_usage(self):
        """Reset usage counters (e.g., for daily reset)."""
        self.call_count = 0
        self.token_count = 0
        self.error_count = 0
