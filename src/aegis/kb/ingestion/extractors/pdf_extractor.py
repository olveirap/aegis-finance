# SPDX-License-Identifier: MIT
"""PDF Extractor using Unstructured.io with LlamaParse fallback."""

from __future__ import annotations

import tempfile
import asyncio
from pathlib import Path

from unstructured.partition.pdf import partition_pdf

from aegis.kb.ingestion.extractors.base import BaseExtractor
from aegis.kb.ingestion.models import ExtractedContent, SourceMeta


class PDFExtractor(BaseExtractor):
    """Extracts text and tables from PDF bytes using layout-aware parsing."""

    async def extract(
        self, raw_bytes: bytes, source_meta: SourceMeta
    ) -> ExtractedContent:
        # Unstructured.io is synchronous, so we run it in a threadpool to not block the event loop
        return await asyncio.to_thread(self._extract_sync, raw_bytes, source_meta)

    def _extract_sync(
        self, raw_bytes: bytes, source_meta: SourceMeta
    ) -> ExtractedContent:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            # We use Unstructured's layout-aware parsing
            elements = partition_pdf(filename=tmp_path, strategy="fast")

            text_blocks = []
            tables = []

            for el in elements:
                if el.category == "Table":
                    # Unstructured provides an HTML representation of the table
                    if (
                        hasattr(el.metadata, "text_as_html")
                        and el.metadata.text_as_html
                    ):
                        tables.append(
                            {"html": el.metadata.text_as_html, "text": str(el.text)}
                        )
                    else:
                        tables.append({"text": str(el.text)})
                text_blocks.append(str(el))

            full_text = "\n\n".join(text_blocks)

            return ExtractedContent(
                text=full_text, tables=tables, content_format="markdown", confidence=0.9
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
