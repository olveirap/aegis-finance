# SPDX-License-Identifier: MIT
"""Unit tests for the KBPipeline (Task 0.3)."""

from __future__ import annotations

import hashlib

import pytest

from aegis.kb.pipeline import DocumentChunk, KBPipeline
from aegis.kb.ingestion.models import RawDocument
from aegis.kb.ontology import SourceType, SubTopic


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_doc(
    text: str = "El BCRA publicó nuevas medidas sobre los CEDEARs y la inflación en Argentina.",
    raw_bytes_hash: str | None = None,
    source_url: str = "https://example.com/article",
    source_type: SourceType = SourceType.BLOG,
    jurisdiction: list[str] | None = None,
    topic_tags: list[SubTopic] | None = None,
) -> RawDocument:
    if raw_bytes_hash is None:
        raw_bytes_hash = hashlib.sha256(text.encode()).hexdigest()
    return RawDocument(
        text=text,
        tables=[],
        content_format="raw_text",
        source_url=source_url,
        source_type=source_type,
        jurisdiction=jurisdiction or ["AR"],
        topic_tags=topic_tags or [],
        raw_bytes_hash=raw_bytes_hash,
    )


# ── minimum length filter ─────────────────────────────────────────────────────


def test_short_doc_is_rejected() -> None:
    """Documents with < 50 tokens must be rejected."""
    pipe = KBPipeline()
    doc = _make_doc(text="Hola mundo")
    chunks = pipe.process(doc)
    assert chunks == []


def test_doc_at_threshold_accepted() -> None:
    """Documents at exactly 50+ tokens must pass the filter."""
    pipe = KBPipeline()
    # ~60 simple words ≈ ~60 tokens
    text = " ".join(["inflación"] * 60)
    doc = _make_doc(text=text, raw_bytes_hash=hashlib.sha256(text.encode()).hexdigest())
    chunks = pipe.process(doc)
    assert len(chunks) >= 1


# ── language detection ────────────────────────────────────────────────────────


def test_english_doc_accepted() -> None:
    pipe = KBPipeline()
    text = " ".join(
        ["The Federal Reserve raised interest rates affecting bond markets globally"] * 5
    )
    doc = _make_doc(text=text, raw_bytes_hash=hashlib.sha256(text.encode()).hexdigest())
    chunks = pipe.process(doc)
    assert len(chunks) >= 1


def test_non_es_en_doc_rejected() -> None:
    """A clearly French text should be rejected."""
    pipe = KBPipeline()
    text = " ".join(
        ["Les marchés financiers européens ont connu une forte volatilité cette semaine"] * 5
    )
    doc = _make_doc(text=text, raw_bytes_hash=hashlib.sha256(text.encode()).hexdigest())
    chunks = pipe.process(doc)
    assert chunks == []


# ── hash-based deduplication ───────────────────────────────────────────────────


def test_duplicate_hash_rejected() -> None:
    """Second call with same raw_bytes_hash must return empty list."""
    seen = set()
    pipe = KBPipeline(seen_hashes=seen)
    text = " ".join(["finanzas argentinas mercado bursátil inflación"] * 15)
    h = hashlib.sha256(text.encode()).hexdigest()
    doc = _make_doc(text=text, raw_bytes_hash=h)

    first = pipe.process(doc)
    assert len(first) >= 1

    second = pipe.process(doc)
    assert second == [], "Second processing of same hash must be rejected"


# ── valid document → chunks ───────────────────────────────────────────────────


def test_valid_doc_produces_chunks() -> None:
    pipe = KBPipeline()
    text = (
        "El Banco Central de la República Argentina (BCRA) emitió nuevas medidas "
        "sobre el acceso al mercado de cambios. Los inversores de CEDEARs se vieron "
        "afectados por las restricciones cambiarias. La inflación continúa siendo "
        "un factor clave para las decisiones de inversión en el mercado local. "
        "Los fondos comunes de inversión registraron importantes variaciones durante "
        "la semana."
    )
    doc = _make_doc(text=text, raw_bytes_hash=hashlib.sha256(text.encode()).hexdigest())
    chunks = pipe.process(doc)
    assert len(chunks) >= 1


def test_source_attribution_preserved() -> None:
    """Every chunk must carry the source URL and type from the original document."""
    pipe = KBPipeline()
    text = (
        "La Comisión Nacional de Valores (CNV) publicó nuevas normas sobre "
        "fondos comunes de inversión y CEDEARs en el mercado de capitales argentino. "
        "Estas regulaciones afectan a todos los brokers habilitados por la CNV."
    ) * 3
    url = "https://test-source.com/article"
    doc = _make_doc(
        text=text,
        source_url=url,
        raw_bytes_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    chunks = pipe.process(doc)
    assert chunks, "Expected at least one chunk"
    for chunk in chunks:
        assert chunk.source_url == url
        assert chunk.source_type == SourceType.BLOG


def test_document_chunk_fields() -> None:
    """DocumentChunk must expose all required fields."""
    pipe = KBPipeline()
    text = (
        "La inflación en Argentina afecta los rendimientos de los plazos fijos "
        "y fondos comunes de inversión. El BCRA regula las tasas de interés. "
    ) * 4
    doc = _make_doc(text=text, raw_bytes_hash=hashlib.sha256(text.encode()).hexdigest())
    chunks = pipe.process(doc)
    assert chunks
    ch = chunks[0]
    assert isinstance(ch, DocumentChunk)
    assert ch.chunk_id
    assert ch.chunk_index >= 0
    assert ch.text
    assert ch.n_tokens > 0
    assert ch.source_url
    assert isinstance(ch.topic_tags, list)
    assert isinstance(ch.entities, dict)
    assert 0.0 <= ch.relevance_score <= 1.0
    assert ch.language in ("es", "en")


# ── semantic deduplication (batch path) ───────────────────────────────────────


def test_semantic_dedup_in_batch() -> None:
    """Two near-identical documents in a batch should yield fewer chunks than 2×."""
    pipe = KBPipeline()
    base_text = (
        "La inflación en Argentina alcanzó niveles récord según el INDEC. "
        "El IPC subió un 8 % mensual afectando a ahorristas y trabajadores. "
        "Los economistas prevén que la situación continuará siendo compleja."
    ) * 6
    # Second doc is identical except for a tiny suffix — semantically near-duplicate
    text_a = base_text
    text_b = base_text + " (variante mínima)"

    doc_a = _make_doc(text=text_a, raw_bytes_hash=hashlib.sha256(text_a.encode()).hexdigest())
    doc_b = _make_doc(
        text=text_b,
        source_url="https://other-source.com/article",
        raw_bytes_hash=hashlib.sha256(text_b.encode()).hexdigest(),
    )

    chunks = pipe.process_batch([doc_a, doc_b])
    # Naive (no dedup) would return chunks_a + chunks_b individually.
    # Semantic dedup should collapse near-duplicates.
    solo_a = KBPipeline().process(doc_a)
    solo_b = KBPipeline().process(doc_b)
    naive_total = len(solo_a) + len(solo_b)
    assert len(chunks) < naive_total, (
        f"Expected semantic dedup to reduce chunks; got {len(chunks)} vs naive {naive_total}"
    )


# ── process() docstring contract ─────────────────────────────────────────────


def test_process_docstring_mentions_batch_preference() -> None:
    """Verify the process() method docstring warns about preferring process_batch."""
    import inspect
    doc = inspect.getdoc(KBPipeline.process)
    assert doc and "process_batch" in doc, (
        "process() docstring must mention process_batch() for semantic dedup"
    )
