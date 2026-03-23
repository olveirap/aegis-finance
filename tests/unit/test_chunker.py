# SPDX-License-Identifier: MIT
"""Unit tests for the Chunker (Task 0.3)."""

from __future__ import annotations

import pytest

from aegis.kb.chunker import Chunker, TextChunk


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_long_text(approx_tokens: int) -> str:
    """Return a string that should tokenise to roughly *approx_tokens* tokens."""
    # ~1 token per word for simple ASCII words
    return " ".join(["finance"] * approx_tokens)


# ── construction ─────────────────────────────────────────────────────────────


def test_chunker_defaults() -> None:
    c = Chunker()
    assert c.chunk_size == 512
    assert c.overlap == 64


def test_chunker_custom_params() -> None:
    c = Chunker(chunk_size=256, overlap=32)
    assert c.chunk_size == 256
    assert c.overlap == 32


def test_chunker_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError):
        Chunker(chunk_size=128, overlap=128)  # overlap must be < chunk_size


# ── single-chunk behaviour ────────────────────────────────────────────────────


def test_short_text_produces_single_chunk() -> None:
    c = Chunker(chunk_size=512, overlap=64)
    chunks = c.chunk("Hello world, this is a short sentence.")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, TextChunk)
    assert "Hello world" in chunk.text


def test_empty_text_produces_no_chunks() -> None:
    c = Chunker()
    assert c.chunk("") == []
    assert c.chunk("   ") == []


# ── multi-chunk behaviour ─────────────────────────────────────────────────────


def test_long_text_produces_multiple_chunks() -> None:
    c = Chunker(chunk_size=32, overlap=8)
    text = _make_long_text(100)
    chunks = c.chunk(text)
    assert len(chunks) > 1


def test_chunks_have_correct_token_counts() -> None:
    c = Chunker(chunk_size=32, overlap=8)
    text = _make_long_text(100)
    chunks = c.chunk(text)
    # All chunks except possibly the last must be <= chunk_size tokens
    for ch in chunks[:-1]:
        assert ch.n_tokens <= c.chunk_size


def test_overlap_produces_shared_tokens() -> None:
    """Adjacent chunks should share content proportional to overlap."""
    c = Chunker(chunk_size=32, overlap=8)
    text = _make_long_text(80)
    chunks = c.chunk(text)
    assert len(chunks) >= 2
    # The end of chunk i should appear at the start of chunk i+1
    # (words are identical, so just check that chunk text overlaps)
    words_end = set(chunks[0].text.split()[-4:])
    words_start = set(chunks[1].text.split()[:4])
    assert words_end & words_start, "Adjacent chunks should share tokens via overlap"


def test_chunk_ids_are_unique() -> None:
    c = Chunker(chunk_size=32, overlap=8)
    text = _make_long_text(100)
    chunks = c.chunk(text)
    ids = [ch.chunk_id for ch in chunks]
    assert len(ids) == len(set(ids)), "Each chunk must have a unique chunk_id"


def test_chunk_id_is_sha256() -> None:
    import hashlib

    c = Chunker()
    chunks = c.chunk("Hello world")

    hasher = hashlib.sha256(chunks[0].text.encode())
    hasher.update(b"0")
    expected_id = hasher.hexdigest()

    assert chunks[0].chunk_id == expected_id


# ── TextChunk dataclass ───────────────────────────────────────────────────────


def test_text_chunk_fields() -> None:
    c = Chunker()
    chunks = c.chunk("A quick brown fox")
    ch = chunks[0]
    assert ch.text
    assert ch.n_tokens > 0
    assert ch.chunk_id
    assert ch.chunk_index == 0


def test_chunk_indices_are_sequential() -> None:
    c = Chunker(chunk_size=32, overlap=8)
    text = _make_long_text(100)
    chunks = c.chunk(text)
    assert len(chunks) > 1
    for expected, ch in enumerate(chunks):
        assert ch.chunk_index == expected
