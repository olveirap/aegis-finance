# SPDX-License-Identifier: MIT
"""Storage logic for storing vector embeddings into PostgreSQL.

Defines the `StorageBackend` Protocol and a concrete `PgVectorStore` for pgvector.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

import psycopg

from aegis.kb.embedder import EmbeddedChunk

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """Abstract interface for storing embedded chunks into a database."""

    async def store_batch(self, chunks: list[EmbeddedChunk]) -> None:
        """Store a batch of embedded chunks.
        
        Args:
            chunks: List of valid EmbeddedChunk objects containing both payload and vector.
        """
        ...
        
    async def get_count(self) -> int:
        """Return the total number of chunks stored. Useful for QA."""
        ...
        
    async def initialize(self) -> None:
        """Initialize connection or ensure table existence if needed."""
        ...


class PgVectorStore(StorageBackend):
    """PostgreSQL storage backend using pgvector with psycopg v3.
    
    Args:
        conn_string: Standard DSN for psycopg connection (e.g. postgresql://user:pass@host/db).
    """

    def __init__(self, conn_string: str) -> None:
        self.conn_string = conn_string

    async def initialize(self) -> None:
        """Verify the database connectivity."""
        # Simple health check
        async with await psycopg.AsyncConnection.connect(self.conn_string) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1;")

    async def store_batch(self, chunks: list[EmbeddedChunk]) -> None:
        """Store a batch of embedded chunks using bulk execute_values or executemany.
        
        Uses an upsert logic on `id` (which defaults to a UUID generation via DB) 
        but since we pass no explicit `id`, they will just be inserted.
        Wait, we want to ensure idempotency. The schema specifies UUID PRIMARY KEY DEFAULT gen_random_uuid()
        and doesn't have a unique constraint on chunk_index or source_url.
        Because deduplication is handled by pipeline (Task 0.3) semantic dedup or hash dedup, 
        we rely on pipeline to avoid duplicates at ingest time.
        """
        if not chunks:
            return

        # Prepare parameters
        # id is auto-generated, we specify the rest
        # Columns: content, embedding, source, source_title, source_type, topic_tags, argentina_specific, chunk_index, created_at
        
        query = """
            INSERT INTO kb_chunks (
                content,
                embedding,
                source,
                source_title,
                source_type,
                topic_tags,
                argentina_specific,
                chunk_index
            ) VALUES (
                %s, %s::vector, %s, %s, %s, %s, %s, %s
            )
        """
        
        params_list = []
        for ec in chunks:
            c = ec.chunk
            
            # Extract basic chunk index if present in chunk_id like document_123_chunk_0
            try:
                # Assuming chunker creates ids like "docID_0"
                chunk_index = int(c.chunk_id.split("_")[-1])
            except (ValueError, IndexError):
                chunk_index = 0
                
            # determine argentina specific logic - a simple heuristic based on jurisdiction
            is_ar = "AR" in c.jurisdiction or "ARGENTINA" in [j.upper() for j in c.jurisdiction]
            
            # format tags list
            tags_array = [t.value for t in c.topic_tags]
            
            params_list.append((
                c.text,                        # content
                "[" + ",".join(map(str, ec.embedding)) + "]",  # format as standard vector literal
                c.source_url,                  # source
                c.source_title,                # source_title
                c.source_type.value,           # source_type
                tags_array,                    # topic_tags
                is_ar,                         # argentina_specific
                chunk_index                    # chunk_index
            ))

        async with await psycopg.AsyncConnection.connect(self.conn_string) as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_list)
            await conn.commit()
            
        logger.info(f"Stored {len(chunks)} chunks in pgvector.")

    async def get_count(self) -> int:
        query = "SELECT COUNT(*) FROM kb_chunks;"
        async with await psycopg.AsyncConnection.connect(self.conn_string) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                res = await cur.fetchone()
                return res[0] if res else 0


def get_storage(conn_string: str | None = None) -> StorageBackend:
    """Factory to get the right storage backend."""
    if conn_string is None:
        conn_string = os.environ.get(
            "AEGIS_DB_URL", 
            "postgresql://aegis:aegis_dev@localhost:5432/aegis_finance"
        )
    return PgVectorStore(conn_string)
