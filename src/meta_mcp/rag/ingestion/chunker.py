# ingestion/chunker.py
"""
Structure-aware document chunking with deterministic output.
Splits on document structure first, then by token count with overlap.
"""

import hashlib
import logging
import re
from dataclasses import dataclass

import tiktoken

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A single chunk of document text."""

    text: str
    index: int
    offset_start: int  # Byte offset in source document
    offset_end: int
    chunk_hash: str  # SHA-256 of text content
    token_count: int


class SemanticChunker:
    """
    Structure-aware chunking with configurable parameters.

    Chunking strategy:
    1. Split by document structure (headings, sections)
    2. Further split long sections by token count with overlap
    3. Compute deterministic hash for each chunk
    """

    def __init__(
        self,
        target_tokens: int = 512,
        overlap_tokens: int = 50,
        min_tokens: int = 100,
        max_tokens: int = 2000,
    ):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        # Use cl100k_base encoding (same as GPT-4, close to Gemini tokenization)
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def chunk(self, text: str, mime_type: str = "text/plain") -> list[Chunk]:
        """
        Chunk document text with structure awareness.

        Args:
            text: Full document text
            mime_type: MIME type for structure detection

        Returns:
            List of Chunk objects with stable IDs
        """
        if not text or not text.strip():
            return []

        # Step 1: Split by structure (headings, sections)
        sections = self._split_by_structure(text, mime_type)
        logger.debug(f"Split document into {len(sections)} sections")

        # Step 2: Chunk each section by token bounds
        chunks = []
        global_offset = 0

        for section in sections:
            if not section.strip():
                global_offset += len(section)
                continue

            section_chunks = self._chunk_by_tokens(section, global_offset)
            chunks.extend(section_chunks)
            global_offset += len(section)

        # Step 3: Merge very small chunks
        chunks = self._merge_small_chunks(chunks)

        # Step 4: Assign final indexes and compute hashes
        for i, chunk in enumerate(chunks):
            chunk.index = i
            chunk.chunk_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            chunk.token_count = len(self.encoder.encode(chunk.text))

        logger.info(f"Created {len(chunks)} chunks from document")
        return chunks

    def _split_by_structure(self, text: str, mime_type: str) -> list[str]:
        """Split document by structural boundaries."""

        if mime_type in ["text/markdown", "text/x-markdown"]:
            # Split on markdown headings (# through ###)
            # Keep the heading with its content
            pattern = r"(?=^#{1,3}\s+)"
            sections = re.split(pattern, text, flags=re.MULTILINE)
        elif mime_type == "text/plain":
            # Split on double newlines (paragraph boundaries)
            # Also split on lines that look like headers (ALL CAPS, numbered)
            sections = re.split(r"\n\n+", text)
        else:
            # For other types, split on double newlines
            sections = re.split(r"\n\n+", text)

        # Filter empty sections and clean whitespace
        sections = [s.strip() for s in sections if s.strip()]

        return sections

    def _chunk_by_tokens(self, text: str, base_offset: int) -> list[Chunk]:
        """Split text into chunks of target_tokens with overlap."""

        tokens = self.encoder.encode(text)

        # If text fits in one chunk, return as-is
        if len(tokens) <= self.target_tokens:
            return [
                Chunk(
                    text=text,
                    index=-1,  # Set later
                    offset_start=base_offset,
                    offset_end=base_offset + len(text),
                    chunk_hash="",  # Set later
                    token_count=len(tokens),
                )
            ]

        chunks = []
        i = 0

        while i < len(tokens):
            # Get chunk tokens
            end_idx = min(i + self.target_tokens, len(tokens))
            chunk_tokens = tokens[i:end_idx]
            chunk_text = self.encoder.decode(chunk_tokens)

            # Calculate byte offsets
            # Note: This is approximate due to token-to-byte mapping
            prefix_text = self.encoder.decode(tokens[:i])
            offset_start = base_offset + len(prefix_text.encode("utf-8"))
            offset_end = offset_start + len(chunk_text.encode("utf-8"))

            chunks.append(
                Chunk(
                    text=chunk_text,
                    index=-1,
                    offset_start=offset_start,
                    offset_end=offset_end,
                    chunk_hash="",
                    token_count=len(chunk_tokens),
                )
            )

            # Move forward, leaving overlap
            step = self.target_tokens - self.overlap_tokens
            i += max(step, 1)  # Ensure we always move forward

        return chunks

    def _merge_small_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Merge chunks that are too small."""
        if not chunks:
            return chunks

        merged = []
        current = None

        for chunk in chunks:
            if current is None:
                current = chunk
            elif current.token_count < self.min_tokens:
                # Merge with next chunk
                current.text = current.text + "\n\n" + chunk.text
                current.offset_end = chunk.offset_end
                current.token_count = len(self.encoder.encode(current.text))
            else:
                merged.append(current)
                current = chunk

        if current is not None:
            merged.append(current)

        return merged

    def estimate_chunk_count(self, text: str) -> int:
        """Estimate number of chunks for a document (without actually chunking)."""
        tokens = len(self.encoder.encode(text))
        if tokens <= self.target_tokens:
            return 1

        step = self.target_tokens - self.overlap_tokens
        return max(1, (tokens - self.overlap_tokens) // step + 1)
