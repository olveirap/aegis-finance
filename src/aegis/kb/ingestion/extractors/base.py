# SPDX-License-Identifier: MIT
"""Base abstraction for ingestion extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from aegis.kb.ingestion.models import ExtractedContent, SourceMeta


class BaseExtractor(ABC):
    """Abstract base class for all data extractors.
    
    Extractors take raw bytes (or previously extracted output if chained)
    and parse it into structured ExtractedContent.
    """

    @abstractmethod
    async def extract(self, raw_bytes: bytes, source_meta: SourceMeta) -> ExtractedContent:
        """Extracts text and tables from raw bytes.
        
        Args:
            raw_bytes: Raw bytes representing the document content.
            source_meta: The source metadata associated with these bytes.
            
        Returns:
            Structured ExtractedContent containing the text and optional tables.
        """
        pass
