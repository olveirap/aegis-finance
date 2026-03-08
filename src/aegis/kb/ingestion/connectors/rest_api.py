# SPDX-License-Identifier: MIT
"""REST API Connector.

Used for pulling structured JSON/XML datasets from APIs like FRED, ECB, IOL.
"""

from __future__ import annotations

import hashlib
import os
from typing import AsyncIterator

from aegis.common.http_client import ResilientHTTPClient
from aegis.kb.ingestion.connectors.base import BaseConnector
from aegis.kb.ingestion.models import SourceMeta
from aegis.kb.ingestion.registry import SourceConfig
from aegis.kb.ontology import SourceType


class RESTAPIConnector(BaseConnector):
    """Fetches data from REST APIs, returning raw bytes (JSON/XML)."""

    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        
        if not config.base_url:
            raise ValueError(f"Source '{config.name}' requires a base_url for REST API")

        headers = {}
        if config.auth:
            if config.auth.type == "api_key" and config.auth.env:
                api_key = os.getenv(config.auth.env)
                if not api_key:
                    raise ValueError(f"Missing environment variable {config.auth.env} for auth")
                
                auth_param_name = config.params.get("auth_param_name")
                if auth_param_name:
                    config.params[auth_param_name] = api_key
                else:
                    headers["Authorization"] = f"Bearer {api_key}"

        max_concurrent = config.params.get("max_concurrent", 5)
        client = ResilientHTTPClient(max_concurrent=max_concurrent, headers=headers)
        
        try:
            req_params = {k: v for k, v in config.params.items() if k not in ["max_concurrent", "auth_param_name"]}
            
            response = await client.get(config.base_url, params=req_params)
            
            raw_bytes = response.content
            bytes_hash = hashlib.sha256(raw_bytes).hexdigest()
            
            meta = SourceMeta(
                source_url=str(response.url),
                source_type=SourceType.API_TIMESERIES, 
                jurisdiction=config.jurisdiction,
                topic_tags=config.ontology_tags,
                raw_bytes_hash=bytes_hash,
                last_seen_id=None,
            )
            
            yield raw_bytes, meta

        finally:
            await client.aclose()
