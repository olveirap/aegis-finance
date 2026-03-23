# SPDX-License-Identifier: MIT
"""Storage logic for storing vector embeddings into PostgreSQL.

Defines the `StorageBackend` Protocol and a concrete `PgVectorStore` for pgvector.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Protocol

from psycopg_pool import ConnectionPool

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

    async def close(self) -> None:
        """Close connection pool and clean up resources."""
        ...


class PgVectorStore(StorageBackend):
    """PostgreSQL storage backend using pgvector with synchronous psycopg v3 + thread pool.

    This avoids the asyncio Windows ProactorEventLoop vs SelectorEventLoop conflict
    that occurs when Playwright (Proactor) and psycopg async (Selector) run together.

    Args:
        conn_string: Standard DSN for psycopg connection (e.g. postgresql://user:pass@host/db).
    """

    def __init__(self, conn_string: str) -> None:
        self.conn_string = conn_string
        # Use a synchronous connection pool
        self.pool = ConnectionPool(
            conninfo=self.conn_string,
            min_size=1,
            max_size=10,
            open=False,  # Do not open until initialize
        )

    async def initialize(self) -> None:
        """Initialize connection pool and verify the database connectivity."""
        await asyncio.to_thread(self.pool.open)

        def _check():
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")

        await asyncio.to_thread(_check)

    async def store_batch(self, chunks: list[EmbeddedChunk]) -> None:
        """Store a batch of embedded chunks using bulk execute_values or executemany."""
        if not chunks:
            return

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
            chunk_index = c.chunk_index
            is_ar = "AR" in c.jurisdiction or "ARGENTINA" in [
                j.upper() for j in c.jurisdiction
            ]
            tags_array = [t.value for t in c.topic_tags]

            params_list.append(
                (
                    c.text,
                    "[" + ",".join(map(str, ec.embedding)) + "]",
                    c.source_url,
                    c.source_title,
                    c.source_type.value,
                    tags_array,
                    is_ar,
                    chunk_index,
                )
            )

        def _insert():
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, params_list)
                conn.commit()

        await asyncio.to_thread(_insert)
        logger.info(f"Stored {len(chunks)} chunks in pgvector.")

    async def get_count(self) -> int:
        query = "SELECT COUNT(*) FROM kb_chunks;"

        def _count():
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    res = cur.fetchone()
                    return res[0] if res else 0

        return await asyncio.to_thread(_count)

    async def close(self) -> None:
        """Close connection pool."""

        def _close():
            self.pool.close()

        await asyncio.to_thread(_close)


def get_storage(conn_string: str | None = None) -> StorageBackend:
    """Factory to get the right storage backend."""
    if conn_string is None:
        conn_string = os.environ.get(
            "AEGIS_DB_URL", "postgresql://aegis:aegis_dev@localhost:5432/aegis_finance"
        )
    return PgVectorStore(conn_string)
