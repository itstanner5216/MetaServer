"""
Lightweight embedding system for tool descriptions.

Uses simple TF-IDF word-based embeddings to avoid heavy ML dependencies.
Focuses on correctness and speed over sophistication.
"""

import math
import re
from collections import Counter

from ..registry.models import ToolRecord


class ToolEmbedder:
    """
    Generate embeddings for tools using TF-IDF word vectors.

    Simple, dependency-free approach:
    1. Tokenize text into words
    2. Build vocabulary from all tool descriptions
    3. Generate TF-IDF vectors
    4. Normalize to unit length for cosine similarity

    Cache embeddings to avoid recomputation.
    """

    def __init__(self):
        """Initialize embedder with empty cache and vocabulary."""
        self._cache: dict[str, list[float]] = {}  # tool_id -> embedding vector
        self._vocabulary: set[str] = set()
        self._vocab_list: list[str] = []  # Cached sorted vocabulary (PERF-001)
        self._idf_scores: dict[str, float] = {}
        self._document_count = 0

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text into lowercase words.

        Args:
            text: Input text to tokenize

        Returns:
            List of lowercase word tokens
        """
        # Convert to lowercase and extract words (alphanumeric + underscore)
        text = text.lower()
        # Split on non-alphanumeric characters, keep underscores
        words = re.findall(r"[a-z0-9_]+", text)
        return words

    def _build_vocabulary(self, tools: list[ToolRecord]) -> None:
        """
        Build vocabulary and IDF scores from tool corpus.

        Args:
            tools: List of ToolRecord objects to build vocabulary from
        """
        if not tools:
            return

        self._document_count = len(tools)
        if self._document_count == 0:  # Defensive check
            return

        document_frequency: dict[str, int] = Counter()

        # Count document frequency for each word
        for tool in tools:
            # Combine description and tags into searchable text
            text = f"{tool.description_1line} {tool.description_full} {' '.join(tool.tags)}"
            words = set(self._tokenize(text))

            for word in words:
                document_frequency[word] += 1
                self._vocabulary.add(word)

        # Calculate IDF scores: log((N + 1) / (df + 1)) + 1
        # Using smoothed IDF with constant offset to ensure all scores > 0
        # This prevents zero vectors when words appear in all documents
        for word, df in document_frequency.items():
            if df > 0 and self._document_count > 0:  # Defensive check
                self._idf_scores[word] = math.log((self._document_count + 1) / (df + 1)) + 1.0

        # Cache sorted vocabulary for faster vector conversion (PERF-001)
        self._vocab_list = sorted(self._vocabulary)

    def _compute_tf_idf(self, text: str) -> dict[str, float]:
        """
        Compute TF-IDF scores for text.

        Args:
            text: Input text to compute scores for

        Returns:
            Dictionary mapping words to TF-IDF scores
        """
        words = self._tokenize(text)
        if not words:
            return {}

        # Calculate term frequency
        word_counts = Counter(words)
        total_words = len(words)

        tf_idf: dict[str, float] = {}
        for word, count in word_counts.items():
            if word in self._vocabulary:
                tf = count / total_words
                idf = self._idf_scores.get(word, 0.0)
                tf_idf[word] = tf * idf

        return tf_idf

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        """
        Normalize vector to unit length.

        Args:
            vector: Input vector to normalize

        Returns:
            Unit-length normalized vector
        """
        magnitude = math.sqrt(sum(x * x for x in vector))
        if magnitude == 0:
            return vector
        return [x / magnitude for x in vector]

    def _tf_idf_to_vector(self, tf_idf: dict[str, float]) -> list[float]:
        """
        Convert TF-IDF scores to fixed-length vector.

        Args:
            tf_idf: TF-IDF scores by word

        Returns:
            Fixed-length embedding vector
        """
        # Use cached sorted vocabulary (updated in _build_vocabulary) - PERF-001
        # Fallback to sorting if cache not populated (defensive programming)
        vocab_list = self._vocab_list if self._vocab_list else sorted(self._vocabulary)

        # Build vector in vocabulary order
        vector = [tf_idf.get(word, 0.0) for word in vocab_list]

        return self._normalize_vector(vector)

    def build_index(self, tools: list[ToolRecord]) -> None:
        """
        Build embedding index from all registered tools.

        This must be called before embed_tool() or embed_query().

        Args:
            tools: List of all ToolRecord objects to index
        """
        # Build vocabulary and IDF scores
        self._build_vocabulary(tools)

        # Pre-compute embeddings for all tools
        self._cache.clear()
        for tool in tools:
            embedding = self.embed_tool(tool)
            self._cache[tool.tool_id] = embedding

    def embed_tool(self, tool: ToolRecord) -> list[float]:
        """
        Generate embedding for a tool based on description and tags.

        Combines:
        - description_1line (high weight)
        - description_full (medium weight)
        - tags (high weight)

        Args:
            tool: ToolRecord to generate embedding for

        Returns:
            Normalized embedding vector
        """
        # Check cache first
        if tool.tool_id in self._cache:
            return self._cache[tool.tool_id]

        # Combine all text fields with appropriate weighting
        # Tags and 1-line description are more important for matching
        text = (
            f"{tool.description_1line} {tool.description_1line} "  # Double weight
            f"{tool.description_full} "
            f"{' '.join(tool.tags)} {' '.join(tool.tags)}"  # Double weight
        )

        # Compute TF-IDF and convert to vector
        tf_idf = self._compute_tf_idf(text)
        vector = self._tf_idf_to_vector(tf_idf)

        # Cache the result
        self._cache[tool.tool_id] = vector

        return vector

    def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for search query.

        Uses same approach as tool embedding for consistency.

        Args:
            query: Search query string

        Returns:
            Normalized embedding vector (empty list if no vocabulary built)
        """
        if not query or not query.strip():
            # Return zero vector matching vocabulary size
            # If no vocabulary built, return empty list
            if not self._vocabulary:
                return []
            return [0.0] * len(self._vocabulary)

        # Compute TF-IDF for query
        tf_idf = self._compute_tf_idf(query)
        vector = self._tf_idf_to_vector(tf_idf)

        return vector

    def get_cached_embedding(self, tool_id: str) -> list[float]:
        """
        Get cached embedding for a tool.

        Args:
            tool_id: Tool identifier

        Returns:
            Cached embedding vector, or empty vector if not cached
        """
        return self._cache.get(tool_id, [0.0] * len(self._vocabulary))

    def clear_cache(self) -> None:
        """Clear embedding cache."""
        self._cache.clear()
        self._vocab_list.clear()  # Clear cached sorted vocabulary (PERF-001)
