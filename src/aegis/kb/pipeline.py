# SPDX-License-Identifier: MIT
"""End-to-end KB quality pipeline (Task 0.3).

Processes ``RawDocument`` objects produced by the ingestion framework (Task 0.2)
and emits quality-filtered ``DocumentChunk`` objects ready for embedding (Task 0.4).

Pipeline stages (in order)
---------------------------
1. Content-hash deduplication (SHA-256 via ``RawDocument.raw_bytes_hash``)
2. Minimum-length filter (< 50 tokens → discard)
3. Language detection (keep ``es`` / ``en`` only)
4. Chunking (``Chunker``, default 512 tokens / 64 overlap)
5. Relevance scoring (TF-IDF cosine vs. per-subtopic keyword bags)
6. Semantic deduplication — **batch path only** (TF-IDF cosine > 0.95 → collapse)
7. Ontology tagging (``HeuristicTagger``)
8. Entity extraction (``HeuristicExtractor``)

Semantic deduplication scope
-----------------------------
Semantic dedup runs only within a single ``process_batch()`` call.
Cross-batch dedup (across pipeline runs) is deferred to Task 0.4.
TODO(Task 0.4): Implement cross-batch semantic dedup via an ANN query against
pgvector to detect near-duplicate chunks at ingest time.
"""

from __future__ import annotations

import logging
from typing import Any

import tiktoken
from langdetect import detect, LangDetectException
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from aegis.kb.chunker import Chunker
from aegis.kb.extractor import HeuristicExtractor
from aegis.kb.ingestion.models import RawDocument
from aegis.kb.ontology import SubTopic, SourceType
from aegis.kb.tagger import HeuristicTagger
from aegis.kb.temporal import TemporalInterval

logger = logging.getLogger(__name__)

# Minimum token count; docs below this threshold are discarded.
_MIN_TOKENS = 50

# Accepted language codes (langdetect output).
_ACCEPTED_LANGS = frozenset(["es", "en"])

# Cosine-similarity threshold above which two chunks are considered semantic duplicates.
_SEMANTIC_DUP_THRESHOLD = 0.95

# TF-IDF keyword bags for relevance scoring (one per SubTopic).
# These mirror the keyword map in tagger.py and are reused for scoring.
_SUBTOPIC_KEYWORD_BAGS: dict[SubTopic, str] = {
    SubTopic.BUDGETING: "presupuesto budget gastos expenses household",
    SubTopic.SAVING: "ahorro saving savings reserva",
    SubTopic.EMERGENCY_FUND: "fondo emergencia emergency fund colchon",
    SubTopic.DEBT_MANAGEMENT: "deuda debt credito refinanciacion prestamo",
    SubTopic.INSURANCE: "seguro insurance cobertura poliza",
    SubTopic.STOCKS: "accion acciones stock stocks equity bolsa",
    SubTopic.BONDS: "bono bonos bond bonds renta fija fixed income",
    SubTopic.CEDEARS: "cedear cedears",
    SubTopic.FCIS: "fondo comun fci mutual fund",
    SubTopic.ETFS: "etf etfs exchange traded fund",
    SubTopic.CRYPTO: "crypto bitcoin ethereum criptomoneda criptoactivo",
    SubTopic.MUTUAL_FUNDS: "fondo mutuo mutual fund",
    SubTopic.INCOME_TAX: "ganancias income tax impuesto",
    SubTopic.WEALTH_TAX: "bienes personales wealth tax patrimonio",
    SubTopic.CURRENCY_CONTROLS: "cepo mep ccl dolar blue controles cambiarios",
    SubTopic.INFLATION: "inflacion inflation ipc cpi indec precio precios",
    SubTopic.REGULATORY_BODIES: "bcra cnv afip uif banco central regulador",
    SubTopic.TAX_PLANNING: "planificacion fiscal tax planning declaracion",
    SubTopic.MORTGAGE: "hipoteca mortgage credito hipotecario",
    SubTopic.RENTAL: "alquiler rental inquilino arrendamiento",
    SubTopic.PROPERTY_TAX: "abl inmobiliario property tax",
}


# ── Output model ──────────────────────────────────────────────────────────────


class DocumentChunk(BaseModel):
    """A quality-filtered, tagged chunk ready for embedding."""

    chunk_id: str
    text: str
    n_tokens: int
    source_url: str
    source_title: str | None = None
    source_type: SourceType
    jurisdiction: list[str]
    topic_tags: list[SubTopic]
    relevance_score: float
    language: str
    entities: dict[str, Any]
    temporal_metadata: TemporalInterval | None = None


# ── Pipeline ──────────────────────────────────────────────────────────────────


class KBPipeline:
    """Orchestrates all quality stages and produces ``DocumentChunk`` objects.

    Args:
        seen_hashes:
            A mutable ``set`` of SHA-256 hashes already processed.  Pass a
            shared set across multiple ``process`` / ``process_batch`` calls to
            enable content-hash deduplication across invocations.  When ``None``
            (default), a fresh set is created per ``KBPipeline`` instance.
        chunker:
            Optional ``Chunker`` override.  Defaults to ``Chunker(512, 64)``.
    """

    def __init__(
        self,
        seen_hashes: set[str] | None = None,
        chunker: Chunker | None = None,
    ) -> None:
        self._seen_hashes: set[str] = seen_hashes if seen_hashes is not None else set()
        self._chunker = chunker or Chunker(chunk_size=512, overlap=64)
        self._tagger = HeuristicTagger()
        self._extractor = HeuristicExtractor()
        self._enc = tiktoken.get_encoding("cl100k_base")

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, doc: RawDocument) -> list[DocumentChunk]:
        """Process a single ``RawDocument`` through all quality stages.

        Stages applied: hash dedup → length filter → language detection →
        chunking → relevance scoring → tagging → entity extraction.

        .. note::
            Semantic deduplication is **not** applied to single-document calls.
            Prefer ``process_batch()`` when dedup guarantees are required,
            especially when multiple documents in a single run may be
            near-duplicates of one another.

        Returns:
            A list of ``DocumentChunk`` objects, or an empty list if the
            document is rejected at any quality gate.
        """
        # ── Stage 1: content-hash dedup ───────────────────────────────────────
        if doc.raw_bytes_hash in self._seen_hashes:
            logger.debug("Rejected (duplicate hash): %s", doc.source_url)
            return []
        self._seen_hashes.add(doc.raw_bytes_hash)

        # ── Stage 2: minimum-length filter ────────────────────────────────────
        token_ids = self._enc.encode(doc.text.strip())
        if len(token_ids) < _MIN_TOKENS:
            logger.debug("Rejected (< %d tokens): %s", _MIN_TOKENS, doc.source_url)
            return []

        # ── Stage 3: language detection ───────────────────────────────────────
        try:
            lang = detect(doc.text)
        except LangDetectException:
            logger.debug("Rejected (language detection failed): %s", doc.source_url)
            return []

        if lang not in _ACCEPTED_LANGS:
            logger.debug("Rejected (language=%s): %s", lang, doc.source_url)
            return []

        # ── Stage 4: chunking ─────────────────────────────────────────────────
        text_chunks = self._chunker.chunk(doc.text)
        if not text_chunks:
            return []

        # ── Stages 5 / 7 / 8: score + tag + extract per chunk ────────────────
        return [
            self._build_chunk(tc.text, tc.n_tokens, tc.chunk_id, doc, lang)
            for tc in text_chunks
        ]

    def process_batch(self, docs: list[RawDocument]) -> list[DocumentChunk]:
        """Process a batch of documents, applying semantic deduplication.

        Semantic dedup scope: within this batch only.
        Cross-batch dedup is deferred to Task 0.4 (pgvector ANN query).

        Args:
            docs: Documents to process.

        Returns:
            Deduplicated list of ``DocumentChunk`` objects.
        """
        all_chunks: list[DocumentChunk] = []
        for doc in docs:
            all_chunks.extend(self.process(doc))

        if len(all_chunks) < 2:
            return all_chunks

        return self._semantic_dedup(all_chunks)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_chunk(
        self,
        text: str,
        n_tokens: int,
        chunk_id: str,
        doc: RawDocument,
        lang: str,
    ) -> DocumentChunk:
        """Build a single ``DocumentChunk`` with tags, score, and entities."""
        topic_tags = self._tagger.tag(text)
        relevance_score = self._relevance_score(text)
        entities = self._extractor.extract(text).to_dict()

        return DocumentChunk(
            chunk_id=chunk_id,
            text=text,
            n_tokens=n_tokens,
            source_url=doc.source_url,
            source_title=doc.source_title,
            source_type=doc.source_type,
            jurisdiction=doc.jurisdiction,
            topic_tags=topic_tags,
            relevance_score=relevance_score,
            language=lang,
            entities=entities,
            temporal_metadata=doc.temporal_metadata,
        )

    def _relevance_score(self, text: str) -> float:
        """Return max cosine similarity between *text* and any subtopic keyword bag."""
        corpus = list(_SUBTOPIC_KEYWORD_BAGS.values()) + [text]
        try:
            vectorizer = TfidfVectorizer(
                min_df=1, analyzer="word", token_pattern=r"[^\s]+"
            )
            tfidf = vectorizer.fit_transform(corpus)
            doc_vec = tfidf[-1]
            topic_vecs = tfidf[:-1]
            sims = cosine_similarity(doc_vec, topic_vecs).flatten()
            return float(sims.max())
        except ValueError:
            return 0.0

    @staticmethod
    def _semantic_dedup(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Remove near-duplicate chunks within a batch using TF-IDF cosine similarity.

        When two chunks exceed ``_SEMANTIC_DUP_THRESHOLD``, the one with the
        lower ``relevance_score`` is discarded.

        Returns:
            Filtered list with near-duplicates removed.
        """
        if len(chunks) < 2:
            return chunks

        texts = [ch.text for ch in chunks]
        try:
            vectorizer = TfidfVectorizer(min_df=1, analyzer="word", token_pattern=r"[^\s]+")
            tfidf = vectorizer.fit_transform(texts)
        except ValueError:
            return chunks

        sim_matrix = cosine_similarity(tfidf)
        n = len(chunks)
        keep = [True] * n

        for i in range(n):
            if not keep[i]:
                continue
            for j in range(i + 1, n):
                if not keep[j]:
                    continue
                if sim_matrix[i, j] >= _SEMANTIC_DUP_THRESHOLD:
                    # Keep the chunk with higher relevance score.
                    if chunks[i].relevance_score >= chunks[j].relevance_score:
                        keep[j] = False
                    else:
                        keep[i] = False
                        break  # i is discarded; move to next i

        return [ch for ch, k in zip(chunks, keep) if k]
