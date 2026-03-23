# SPDX-License-Identifier: MIT
"""TimeSeries Extractor.

Normalizes arrays (FRED, ECB, DolarApi, INDEC) to temporal logic.
"""

from __future__ import annotations

import json

from aegis.kb.ingestion.extractors.base import BaseExtractor
from aegis.kb.ingestion.models import ExtractedContent, SourceMeta


class TimeSeriesExtractor(BaseExtractor):
    """Normalizes JSON observation arrays to temporal metadata."""

    async def extract(
        self, raw_bytes: bytes, source_meta: SourceMeta
    ) -> ExtractedContent:
        data = json.loads(raw_bytes)

        # Example naive normalization rule that will be expanded per-source
        # Returns raw JSON string as text with timeseries format
        return ExtractedContent(
            text=json.dumps(data, indent=2),
            tables=[],
            content_format="timeseries",
            confidence=1.0,
            temporal_metadata=None,
        )
