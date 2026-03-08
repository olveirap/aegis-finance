# SPDX-License-Identifier: MIT
"""HTML Extractor using crawl4ai for rendered DOM extraction."""

from __future__ import annotations

import json
from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import NoExtractionStrategy

from aegis.kb.ingestion.extractors.base import BaseExtractor
from aegis.kb.ingestion.models import ExtractedContent, SourceMeta


class HTMLExtractor(BaseExtractor):
    """Converts raw HTML bytes to Markdown using crawl4ai."""

    async def extract(self, raw_bytes: bytes, source_meta: SourceMeta) -> ExtractedContent:
        url = source_meta.source_url
        
        # In a real environment, we'd reuse the crawler instance, 
        # but for safety against complex memory leaks in headless browsers:
        async with AsyncWebCrawler(verbose=False) as crawler:
            # We can pass raw_html directly to crawl4ai
            result = await crawler.arun(
                url=url,
                raw_html=raw_bytes.decode("utf-8", errors="ignore"),
                extraction_strategy=NoExtractionStrategy(),
                bypass_cache=True,
            )
            
            tables = []
            
            return ExtractedContent(
                text=result.markdown,
                tables=tables,
                content_format="markdown",
                confidence=0.85 if result.success else 0.0
            )
