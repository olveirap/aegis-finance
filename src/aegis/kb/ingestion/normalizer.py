# SPDX-License-Identifier: MIT
"""Normalizer converts extracted content into a unified RawDocument format."""

from __future__ import annotations

from aegis.kb.ingestion.models import ExtractedContent, RawDocument, SourceMeta
from aegis.kb.ingestion.registry import SourceConfig


class Normalizer:
    """Combines metadata and extracted content into a RawDocument."""

    @staticmethod
    def normalize(
        extracted: ExtractedContent, source_meta: SourceMeta, config: SourceConfig
    ) -> RawDocument:
        """Constructs a unified RawDocument structure."""

        return RawDocument(
            text=extracted.text,
            tables=extracted.tables,
            content_format=extracted.content_format,
            source_url=source_meta.source_url,
            source_type=source_meta.source_type,
            jurisdiction=source_meta.jurisdiction,
            topic_tags=source_meta.topic_tags,
            raw_bytes_hash=source_meta.raw_bytes_hash,
            temporal_metadata=extracted.temporal_metadata,
        )
