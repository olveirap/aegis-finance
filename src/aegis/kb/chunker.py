# SPDX-License-Identifier: MIT
"""Token-aware text chunker for the KB quality pipeline.

Uses tiktoken (cl100k_base) to split long texts into overlapping windows.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import tiktoken


@dataclass
class TextChunk:
    """A single chunk of text with token count and a stable content hash."""

    chunk_id: str
    text: str
    n_tokens: int


class Chunker:
    """Splits text into overlapping token windows.

    Args:
        chunk_size: Maximum number of tokens per chunk (default 512).
        overlap: Number of tokens shared between consecutive chunks (default 64).

    Raises:
        ValueError: If overlap >= chunk_size.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        if overlap >= chunk_size:
            raise ValueError(
                f"overlap ({overlap}) must be strictly less than chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._enc = tiktoken.get_encoding("cl100k_base")

    # ── public API ────────────────────────────────────────────────────────────

    def chunk(self, text: str) -> list[TextChunk]:
        """Split *text* into overlapping ``TextChunk`` objects.

        Returns an empty list for whitespace-only input.
        """
        stripped = text.strip()
        if not stripped:
            return []

        token_ids = self._enc.encode(stripped)
        if not token_ids:
            return []

        chunks: list[TextChunk] = []
        step = self.chunk_size - self.overlap
        start = 0

        i = 0
        while start < len(token_ids):
            end = min(start + self.chunk_size, len(token_ids))
            window = token_ids[start:end]
            chunk_text = self._enc.decode(window)
            
            # Incorporate the chunk index into the hash to prevent collisions
            # when a document contains repeated identical text patterns.
            hasher = hashlib.sha256(chunk_text.encode())
            hasher.update(str(i).encode())
            chunk_id = hasher.hexdigest()
            
            chunks.append(TextChunk(chunk_id=chunk_id, text=chunk_text, n_tokens=len(window)))
            if end == len(token_ids):
                break
            start += step
            i += 1

        return chunks
