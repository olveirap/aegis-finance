# SPDX-License-Identifier: MIT
"""Async PostgreSQL connection pool for Aegis Finance.

Provides a module-level singleton pool using psycopg v3 and psycopg_pool.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

DEFAULT_DSN = "postgresql://aegis:aegis_dev@localhost:5432/aegis_finance"

_pool: AsyncConnectionPool | None = None


async def get_pool(dsn: str | None = None) -> AsyncConnectionPool:
    """Return the module-level connection pool, creating it on first call.

    Args:
        dsn: PostgreSQL connection string.  Falls back to the ``AEGIS_DB_URL``
             environment variable, then to :data:`DEFAULT_DSN`.

    Returns:
        A warmed-up :class:`AsyncConnectionPool`.
    """
    global _pool  # noqa: PLW0603

    if _pool is None:
        if dsn is None:
            dsn = os.environ.get("AEGIS_DB_URL", DEFAULT_DSN)
        _pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=2,
            max_size=10,
            open=False,
        )
        await _pool.open()

    return _pool


@asynccontextmanager
async def get_connection() -> AsyncIterator[AsyncConnection]:
    """Yield an async connection from the pool.

    Usage::

        async with get_connection() as conn:
            await conn.execute("SELECT 1")
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn


async def check_health(pool: AsyncConnectionPool) -> bool:
    """Run a trivial query to verify database connectivity.

    Args:
        pool: An open :class:`AsyncConnectionPool`.

    Returns:
        ``True`` if the database is reachable.

    Raises:
        Exception: Propagates any database error.
    """
    async with pool.connection() as conn:
        await conn.execute("SELECT 1")
    return True


async def close_pool() -> None:
    """Close the module-level pool if it exists."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None
