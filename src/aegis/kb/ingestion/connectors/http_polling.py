# SPDX-License-Identifier: MIT
"""HTTP Polling Connector.

Used for scraping generic HTML/PDF endpoints that don't have API structures.
Features configurable GET/POST with throttles and retry logic via ResilientHTTPClient.
"""

from __future__ import annotations

import hashlib
from typing import AsyncIterator

from aegis.common.http_client import ResilientHTTPClient
from aegis.kb.ingestion.connectors.base import BaseConnector
from aegis.kb.ingestion.models import SourceMeta
from aegis.kb.ingestion.registry import SourceConfig
from aegis.kb.ontology import SourceType


class HTTPPollingConnector(BaseConnector):
    """Fetches raw documents from HTTP endpoints."""

    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        
        if not config.base_url:
            raise ValueError(f"Source '{config.name}' requires a base_url for HTTP polling")

        # Rate limiting configuration (per source group, e.g., 5 concurrent)
        max_concurrent = config.params.get("max_concurrent", 5)
        
        client = ResilientHTTPClient(max_concurrent=max_concurrent)
        
        try:
            method = config.params.get("method", "GET").upper()
            
            # Additional params for POST body or GET query string
            req_params = config.params.get("query_params", {})
            
            if method == "GET":
                response = await client.get(config.base_url, params=req_params)
            else:
                response = await client.post(config.base_url, json=req_params)

            raw_bytes = response.content
            bytes_hash = hashlib.sha256(raw_bytes).hexdigest()
            
            meta = SourceMeta(
                source_url=str(response.url),
                source_type=SourceType.REGULATION if "regulation" in [t.value for t in config.ontology_tags] else SourceType.BLOG,
                jurisdiction=config.jurisdiction,
                topic_tags=config.ontology_tags,
                raw_bytes_hash=bytes_hash,
                extra={"headers": dict(response.headers)}
            )
            
            yield raw_bytes, meta

        finally:
            await client.aclose()
