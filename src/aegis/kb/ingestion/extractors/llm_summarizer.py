# SPDX-License-Identifier: MIT
"""LLM Summarizer extractor using local Qwen.

Used for compressing books or massive texts into Tips & Rules.
"""

from __future__ import annotations

import json

from aegis.kb.ingestion.extractors.base import BaseExtractor
from aegis.kb.ingestion.models import ExtractedContent, SourceMeta


class LLMSummarizerExtractor(BaseExtractor):
    """Takes text (from previous extractor) and summarizes it using LLM."""

    async def extract(self, raw_bytes: bytes, source_meta: SourceMeta) -> ExtractedContent:
        # Expected input is a JSON string of a previous ExtractedContent 
        # but the interface receives bytes. 
        # If it's a chain, runner.py handles passing the previous output.
        try:
            previous_extract = json.loads(raw_bytes)
            _text_to_summarize = previous_extract.get("text", "")
        except Exception:
            _text_to_summarize = raw_bytes.decode("utf-8", errors="ignore")
            
        # TODO: integrate with llama.cpp Qwen 3.5 using langchain or openai-style client
        summary = "Placeholder summary for LLM extraction."
        
        return ExtractedContent(
            text=summary,
            tables=[],
            content_format="markdown",
            confidence=0.7
        )
