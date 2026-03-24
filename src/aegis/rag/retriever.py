# SPDX-License-Identifier: MIT
"""Retriever service for fetching relevant knowledge chunks.

Combines embedding generation and vector search to retrieve context for RAG.
"""

from __future__ import annotations

import logging
from typing import Any

from aegis.kb.storage import get_storage
from aegis.graph.sql_flow import _embed_text  # Reuse local embedding helper

logger = logging.getLogger(__name__)


class Retriever:
    """Service to retrieve relevant chunks from the Knowledge Base."""

    def __init__(self) -> None:
        self.storage = get_storage()

    async def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for a query.

        Args:
            query: The user query (should be sanitized).
            top_k: Number of chunks to retrieve.

        Returns:
            List of chunks with content and metadata.
        """
        try:
            # 1. Embed query
            query_vector = await _embed_text(query)

            # 2. Search (assuming storage is already initialized at app level)
            results = await self.storage.search(query_vector.tolist(), top_k=top_k)

            return results
        except Exception as e:
            logger.error("Retrieval failed: %s", e)
            return []
