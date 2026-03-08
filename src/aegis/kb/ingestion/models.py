# SPDX-License-Identifier: MIT
"""Data models for the ingestion framework."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from aegis.kb.ontology import SourceType, SubTopic
from aegis.kb.temporal import TemporalInterval


class SourceMeta(BaseModel):
    """Metadata emitted by a connector along with the raw bytes."""
    
    source_url: str
    source_type: SourceType
    jurisdiction: list[str] = Field(default_factory=lambda: ["GLOBAL"])
    topic_tags: list[SubTopic] = Field(default_factory=list)
    raw_bytes_hash: str
    last_seen_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ExtractedContent(BaseModel):
    """Structured text and tables emitted by an extractor."""
    
    text: str = Field(description="The primary extracted textual content in Markdown or plain text.")
    tables: list[dict] = Field(default_factory=list, description="Extracted table data, usually as JSON representations.")
    content_format: Literal["markdown", "json", "raw_text", "table_json", "timeseries"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from the extractor.")
    temporal_metadata: TemporalInterval | None = Field(default=None, description="Extracted temporal validity info if applicable (e.g. from timeseries).")


class RawDocument(BaseModel):
    """The unified output of the ingestion pipeline, ready for chunking and embedding."""
    
    text: str
    tables: list[dict]
    content_format: Literal["markdown", "json", "raw_text", "table_json", "timeseries"]
    
    source_url: str
    source_type: SourceType
    jurisdiction: list[str]
    topic_tags: list[SubTopic]
    raw_bytes_hash: str
    
    temporal_metadata: TemporalInterval | None = None
