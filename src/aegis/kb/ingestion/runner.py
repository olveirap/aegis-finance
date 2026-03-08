# SPDX-License-Identifier: MIT
"""Multi-stage orchestration pipeline for source ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from aegis.kb.ingestion.connectors.base import BaseConnector
from aegis.kb.ingestion.connectors.http_polling import HTTPPollingConnector
from aegis.kb.ingestion.connectors.rest_api import RESTAPIConnector
from aegis.kb.ingestion.connectors.rss_feed import RSSFeedConnector
from aegis.kb.ingestion.connectors.video import VideoConnector, WhisperVideoConnector
from aegis.kb.ingestion.connectors.reddit import RedditConnector

from aegis.kb.ingestion.extractors.base import BaseExtractor
from aegis.kb.ingestion.extractors.html_extractor import HTMLExtractor
from aegis.kb.ingestion.extractors.pdf_extractor import PDFExtractor
from aegis.kb.ingestion.extractors.timeseries_extractor import TimeSeriesExtractor
from aegis.kb.ingestion.extractors.llm_summarizer import LLMSummarizerExtractor

from aegis.kb.ingestion.models import ExtractedContent, RawDocument, SourceMeta
from aegis.kb.ingestion.normalizer import Normalizer
from aegis.kb.ingestion.registry import SourceConfig, SourceRegistry
from aegis.kb.ingestion.state import StateManager

logger = logging.getLogger(__name__)


class IngestionRunner:
    """Pipeline orchestrator for the KB ingestion process."""
    
    def __init__(self, registry: SourceRegistry, state_manager: StateManager | None = None) -> None:
        self.registry = registry
        self.state_manager = state_manager or StateManager()
        
    def _get_connector(self, connector_name: str) -> BaseConnector:
        connectors = {
            "http_polling": HTTPPollingConnector,
            "rest_api": RESTAPIConnector,
            "rss_feed": RSSFeedConnector,
            "video": VideoConnector,
            "whisper_video": WhisperVideoConnector,
            "reddit": RedditConnector,
        }
        if connector_name not in connectors:
            raise ValueError(f"Unknown connector type: {connector_name}")
        return connectors[connector_name]()
        
    def _get_extractor(self, extractor_name: str) -> BaseExtractor:
        extractors = {
            "html": HTMLExtractor,
            "pdf": PDFExtractor,
            "timeseries": TimeSeriesExtractor,
            "llm_summarizer": LLMSummarizerExtractor,
        }
        if extractor_name not in extractors:
            raise ValueError(f"Unknown extractor type: {extractor_name}")
        return extractors[extractor_name]()

    async def _run_extractors(
        self, extractor_names: list[str], raw_bytes: bytes, meta: SourceMeta
    ) -> ExtractedContent:
        """Runs a chain of extractors on the raw bytes."""
        current_bytes = raw_bytes
        current_extracted = None
        
        for name in extractor_names:
            extractor = self._get_extractor(name)
            
            if current_extracted is not None:
                current_bytes = json.dumps(current_extracted.model_dump(), default=str).encode("utf-8")
                
            current_extracted = await extractor.extract(current_bytes, meta)
            
        if current_extracted is None:
            current_extracted = ExtractedContent(
                text=current_bytes.decode("utf-8", errors="ignore"),
                tables=[],
                content_format="raw_text",
                confidence=1.0
            )
            
        return current_extracted

    async def run_source_pipeline(self, config: SourceConfig) -> AsyncIterator[RawDocument]:
        """Runs the complete ingestion pipeline for a single source config."""
        
        await self.state_manager.mark_source_running(config.name)
        checkpoint = await self.state_manager.get_checkpoint(config.name)
        
        try:
            # Single-Stage logic
            if not config.stages:
                connector_name = config.connector
                extractor_names = config.extractor
                if isinstance(extractor_names, str):
                    extractor_names = [extractor_names]
                elif extractor_names is None:
                    extractor_names = []
                    
                connector = self._get_connector(connector_name) # type: ignore
                
                async for raw_bytes, meta in connector.fetch(config, checkpoint.state_data):
                    extracted = await self._run_extractors(extractor_names, raw_bytes, meta)
                    doc = Normalizer.normalize(extracted, meta, config)
                    
                    if meta.last_seen_id:
                        checkpoint.last_seen_id = meta.last_seen_id
                    
                    yield doc
            
            # Multi-Stage logic
            else:
                stages = config.stages
                stage_1 = stages[0]
                connector_1 = self._get_connector(stage_1.connector)
                urls_to_fetch = []
                
                async for _, meta_1 in connector_1.fetch(config, checkpoint.state_data):
                    emitted_urls = meta_1.extra.get("document_urls", [])
                    urls_to_fetch.extend(emitted_urls)
                    if meta_1.last_seen_id:
                        checkpoint.last_seen_id = meta_1.last_seen_id
                
                # We assume Stage 2 is HTTP Polling over target_url
                if len(stages) > 1 and urls_to_fetch:
                    stage_2 = stages[1]
                    connector_2 = self._get_connector(stage_2.connector)
                    extractor_names = stage_2.extractor
                    if isinstance(extractor_names, str):
                        extractor_names = [extractor_names]
                    elif extractor_names is None:
                        extractor_names = []
                    
                    for target_url in urls_to_fetch:
                        config_clone = config.model_copy()
                        config_clone.base_url = target_url
                        
                        async for raw_2, meta_2 in connector_2.fetch(config_clone, {}):
                            extracted = await self._run_extractors(extractor_names, raw_2, meta_2)
                            yield Normalizer.normalize(extracted, meta_2, config_clone)

            await self.state_manager.mark_source_idle(config.name)
            
        except Exception as e:
            logger.error(f"Source {config.name} failed: {e}")
            await self.state_manager.mark_source_failed(config.name)


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True)
    args = parser.parse_args()
    
    registry = SourceRegistry.load(args.sources)
    runner = IngestionRunner(registry)
    
    for name, config in registry.sources.items():
        print(f"Running source: {name}")
        async for doc in runner.run_source_pipeline(config):
            print(f"Ingested doc: {doc.source_url[:100]}")

if __name__ == "__main__":
    asyncio.run(main())
