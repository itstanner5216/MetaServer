# retrieval/bm25.py
"""
BM25 lexical search index for hybrid retrieval.

Implements the BM25 (Best Matching 25) algorithm for lexical search.
Used alongside semantic search for hybrid ranking.
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BM25Index:
    """
    In-memory BM25 index for lexical search.

    Builds index from chunk texts, enables keyword matching.
    Uses BM25 ranking algorithm (Okapi BM25 variant).

    BM25 Parameters:
    - k1: Term frequency saturation parameter (default 1.5)
    - b: Document length normalization (default 0.75)

    Example:
        index = BM25Index()
        index.build_index([
            {"chunk_id": "c1", "text": "Python programming language"},
            {"chunk_id": "c2", "text": "JavaScript for web development"}
        ])
        results = index.search("programming", top_k=10)
        # Returns: [("c1", 0.85), ...]
    """

    # BM25 parameters
    k1: float = 1.5
    b: float = 0.75

    # Index storage
    _documents: dict[str, list[str]] = field(default_factory=dict)  # chunk_id -> tokenized words
    _doc_lengths: dict[str, int] = field(default_factory=dict)  # chunk_id -> word count
    _avg_doc_length: float = 0.0
    _doc_freqs: dict[str, int] = field(
        default_factory=dict
    )  # term -> number of docs containing term
    _idf_cache: dict[str, float] = field(default_factory=dict)  # term -> IDF score
    _total_docs: int = 0
    _is_built: bool = False

    def __post_init__(self):
        """Initialize mutable default fields."""
        self._documents = {}
        self._doc_lengths = {}
        self._doc_freqs = {}
        self._idf_cache = {}

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text for BM25 indexing.

        Converts to lowercase, splits on non-alphanumeric characters,
        and filters out very short tokens.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        if not text:
            return []

        # Convert to lowercase and split on non-alphanumeric
        text = text.lower()
        tokens = re.findall(r"[a-z0-9_]+", text)

        # Filter out very short tokens (single chars except common ones)
        tokens = [t for t in tokens if len(t) > 1 or t in {"a", "i"}]

        return tokens

    def build_index(self, chunks: list[dict]) -> None:
        """
        Build BM25 index from chunk texts.

        Args:
            chunks: List of dicts with 'chunk_id' and 'text' keys

        Raises:
            ValueError: If chunks is empty or missing required keys
        """
        if not chunks:
            logger.warning("Building BM25 index with empty chunk list")
            self._is_built = True
            return

        # Reset index
        self._documents.clear()
        self._doc_lengths.clear()
        self._doc_freqs.clear()
        self._idf_cache.clear()

        total_length = 0

        # First pass: tokenize and compute doc lengths
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            text = chunk.get("text", "")

            if not chunk_id:
                logger.warning("Skipping chunk without chunk_id")
                continue

            tokens = self._tokenize(text)
            self._documents[chunk_id] = tokens
            self._doc_lengths[chunk_id] = len(tokens)
            total_length += len(tokens)

        self._total_docs = len(self._documents)

        if self._total_docs == 0:
            logger.warning("No valid chunks found for BM25 index")
            self._is_built = True
            return

        self._avg_doc_length = total_length / self._total_docs

        # Second pass: compute document frequencies
        for tokens in self._documents.values():
            unique_terms = set(tokens)
            for term in unique_terms:
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1

        # Pre-compute IDF scores
        for term, df in self._doc_freqs.items():
            # IDF with smoothing to avoid division by zero
            self._idf_cache[term] = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)

        self._is_built = True
        logger.info(
            f"BM25 index built: {self._total_docs} documents, "
            f"{len(self._doc_freqs)} unique terms, "
            f"avg length {self._avg_doc_length:.1f}"
        )

    def search(self, query: str, top_k: int = 30) -> list[tuple[str, float]]:
        """
        Search for chunks matching query using BM25 scoring.

        Args:
            query: Search query
            top_k: Maximum number of results to return

        Returns:
            List of (chunk_id, score) tuples, sorted by score descending
        """
        if not self._is_built:
            logger.warning("BM25 index not built, returning empty results")
            return []

        if not query:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: dict[str, float] = {}

        for chunk_id, doc_tokens in self._documents.items():
            score = self._score_document(query_tokens, doc_tokens, chunk_id)
            if score > 0:
                scores[chunk_id] = score

        # Sort by score descending and return top_k
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return sorted_results[:top_k]

    def _score_document(
        self, query_tokens: list[str], doc_tokens: list[str], chunk_id: str
    ) -> float:
        """
        Compute BM25 score for a single document.

        Uses the Okapi BM25 formula:
        score(D, Q) = sum(IDF(qi) * (tf(qi, D) * (k1 + 1)) /
                         (tf(qi, D) + k1 * (1 - b + b * |D|/avgdl)))

        Args:
            query_tokens: Tokenized query
            doc_tokens: Tokenized document
            chunk_id: Document identifier

        Returns:
            BM25 score
        """
        doc_length = self._doc_lengths.get(chunk_id, 0)
        if doc_length == 0:
            return 0.0

        # Count term frequencies in document
        term_freqs = Counter(doc_tokens)

        score = 0.0
        for term in query_tokens:
            tf = term_freqs.get(term, 0)
            if tf == 0:
                continue

            idf = self._idf_cache.get(term, 0)
            if idf <= 0:
                continue

            # BM25 scoring formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self._avg_doc_length))

            score += idf * (numerator / denominator)

        return score

    def update_index(self, chunk_id: str, text: str) -> None:
        """
        Add or update a single chunk in the index.

        Note: For bulk updates, prefer rebuild with build_index().
        This method is O(V) where V is vocabulary size.

        Args:
            chunk_id: Unique chunk identifier
            text: Chunk text content
        """
        # Remove existing entry if present
        if chunk_id in self._documents:
            self.remove_from_index(chunk_id)

        # Tokenize new document
        tokens = self._tokenize(text)
        if not tokens:
            return

        # Add to index
        self._documents[chunk_id] = tokens
        self._doc_lengths[chunk_id] = len(tokens)
        self._total_docs += 1

        # Recalculate average document length
        total_length = sum(self._doc_lengths.values())
        self._avg_doc_length = total_length / self._total_docs if self._total_docs > 0 else 0

        # Update document frequencies
        unique_terms = set(tokens)
        for term in unique_terms:
            self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1
            # Invalidate IDF cache for this term
            if term in self._idf_cache:
                del self._idf_cache[term]

        # Recompute IDF for affected terms
        for term in unique_terms:
            df = self._doc_freqs[term]
            self._idf_cache[term] = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)

        logger.debug(f"Updated BM25 index with chunk {chunk_id}")

    def remove_from_index(self, chunk_id: str) -> bool:
        """
        Remove a chunk from the index.

        Args:
            chunk_id: Chunk identifier to remove

        Returns:
            True if chunk was removed, False if not found
        """
        if chunk_id not in self._documents:
            return False

        # Get tokens before removal
        tokens = self._documents[chunk_id]
        unique_terms = set(tokens)

        # Remove from index
        del self._documents[chunk_id]
        del self._doc_lengths[chunk_id]
        self._total_docs -= 1

        # Recalculate average document length
        total_length = sum(self._doc_lengths.values())
        self._avg_doc_length = total_length / self._total_docs if self._total_docs > 0 else 0

        # Update document frequencies
        for term in unique_terms:
            self._doc_freqs[term] = self._doc_freqs.get(term, 0) - 1
            if self._doc_freqs[term] <= 0:
                del self._doc_freqs[term]
                if term in self._idf_cache:
                    del self._idf_cache[term]
            else:
                # Recompute IDF for this term
                df = self._doc_freqs[term]
                self._idf_cache[term] = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)

        logger.debug(f"Removed chunk {chunk_id} from BM25 index")
        return True

    def get_index_stats(self) -> dict:
        """
        Get statistics about the current index.

        Returns:
            Dict with index statistics
        """
        return {
            "total_documents": self._total_docs,
            "unique_terms": len(self._doc_freqs),
            "avg_doc_length": self._avg_doc_length,
            "is_built": self._is_built,
            "k1": self.k1,
            "b": self.b,
        }

    def clear(self) -> None:
        """Clear the entire index."""
        self._documents.clear()
        self._doc_lengths.clear()
        self._doc_freqs.clear()
        self._idf_cache.clear()
        self._total_docs = 0
        self._avg_doc_length = 0.0
        self._is_built = False
        logger.info("BM25 index cleared")
