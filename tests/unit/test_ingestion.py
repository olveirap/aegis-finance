# SPDX-License-Identifier: MIT
"""Unit tests for the new ingestion framework components."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.kb.ingestion.models import SourceMeta, ExtractedContent, RawDocument
from aegis.kb.ingestion.registry import SourceConfig, StageConfig
from aegis.kb.ontology import SourceType, SubTopic


def test_source_meta_construction() -> None:
    meta = SourceMeta(
        source_url="https://example.com",
        source_type=SourceType.BLOG,
        raw_bytes_hash="mockhash",
        jurisdiction=["AR", "US"],
        topic_tags=[SubTopic.BUDGETING]
    )
    assert meta.source_url == "https://example.com"
    assert "AR" in meta.jurisdiction
    assert meta.raw_bytes_hash == "mockhash"


def test_extracted_content_logic() -> None:
    extracted = ExtractedContent(
        text="Sample text",
        tables=[{"id": 1}],
        content_format="markdown",
        confidence=0.95
    )
    assert extracted.text == "Sample text"
    assert len(extracted.tables) == 1
    assert extracted.confidence == 0.95


def test_raw_document_logic() -> None:
    doc = RawDocument(
        text="Sample",
        tables=[],
        content_format="raw_text",
        source_url="https://x.com",
        source_type=SourceType.REDDIT,
        jurisdiction=["GLOBAL"],
        topic_tags=[],
        raw_bytes_hash="xyz"
    )
    assert doc.source_type == SourceType.REDDIT


def test_registry_config_single_stage() -> None:
    config = SourceConfig(
        name="test_source",
        ontology_tags=[SubTopic.INFLATION],
        jurisdiction=["AR"],
        connector="http_polling",
        base_url="https://api.example.com",
        extractor=["html"]
    )
    assert config.connector == "http_polling"
    assert config.extractor == ["html"]


def test_registry_config_multi_stage() -> None:
    config = SourceConfig(
        name="sec_edgar_multi",
        ontology_tags=[],
        jurisdiction=["US"],
        stages=[
            StageConfig(connector="rss_feed"),
            StageConfig(connector="http_polling", extractor=["pdf", "llm_summarizer"])
        ]
    )
    assert len(config.stages) == 2
    assert config.stages[1].extractor == ["pdf", "llm_summarizer"]


def test_registry_config_validation_fail() -> None:
    with pytest.raises(ValidationError):
        # Fails because neither connector nor stages is provided
        SourceConfig(
            name="bad",
            ontology_tags=[],
            jurisdiction=["GLOBAL"],
            base_url="https://bad.com"
        )
