# SPDX-License-Identifier: MIT
"""RSS/Atom Feed Connector.

Uses feedparser to fetch and incrementally yield feed entries.
"""

from __future__ import annotations

import hashlib
import json
from typing import AsyncIterator

import feedparser

from aegis.common.http_client import ResilientHTTPClient
from aegis.kb.ingestion.connectors.base import BaseConnector
from aegis.kb.ingestion.models import SourceMeta
from aegis.kb.ingestion.registry import SourceConfig
from aegis.kb.ontology import SourceType


class RSSFeedConnector(BaseConnector):
    """Fetches articles/notifications incrementally via RSS."""

    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        if not config.base_url:
            raise ValueError(f"Source '{config.name}' requires a base_url for RSS Feed")

        last_seen = checkpoint.get("last_seen_id") if checkpoint else None

        client = ResilientHTTPClient(max_concurrent=1)
        try:
            response = await client.get(config.base_url)
            feed = feedparser.parse(response.content)

            new_last_seen = last_seen

            for entry in feed.entries:
                entry_id = entry.get("id", entry.get("link", ""))

                # Simple chronological stop condition
                if last_seen and entry_id == last_seen:
                    break

                if not new_last_seen:
                    new_last_seen = entry_id

                raw_bytes = json.dumps(dict(entry)).encode("utf-8")
                bytes_hash = hashlib.sha256(raw_bytes).hexdigest()

                meta = SourceMeta(
                    source_url=entry.get("link", config.base_url),
                    source_type=SourceType.RSS_FEED,
                    jurisdiction=config.jurisdiction,
                    topic_tags=config.ontology_tags,
                    raw_bytes_hash=bytes_hash,
                    last_seen_id=entry_id,
                    extra={"document_urls": [entry.get("link")]},
                )

                yield raw_bytes, meta

        finally:
            await client.aclose()
