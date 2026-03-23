# SPDX-License-Identifier: MIT
"""Async PostgreSQL connection pool for Aegis Finance.

Provides a module-level singleton pool using psycopg v3 and psycopg_pool.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from psycopg import AsyncConnection, Connection
from psycopg_pool import AsyncConnectionPool, ConnectionPool

# Configure event loop for Windows compatibility with psycopg
# Windows uses ProactorEventLoop by default, but psycopg requires SelectorEventLoop
if sys.platform == "win32":
    import asyncio
    import selectors

    try:
        loop = asyncio.get_event_loop()
        if isinstance(loop, asyncio.ProactorEventLoop):
            # Set SelectorEventLoop as the default for this process
            asyncio.set_event_loop(asyncio.SelectorEventLoop(selectors.SelectSelector()))
    except RuntimeError:
        # No event loop running, set the default factory
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

DEFAULT_DSN = "postgresql://aegis:aegis_dev@localhost:5432/aegis_finance"

_pool: AsyncConnectionPool | None = None
_sync_pool: ConnectionPool | None = None


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


def get_db_pool(dsn: str | None = None) -> ConnectionPool:
    """Return a synchronous connection pool for use in notebooks.
    
    This is a convenience function for synchronous code (e.g., Jupyter notebooks)
    that don't want to deal with async/await.
    
    Args:
        dsn: PostgreSQL connection string. Falls back to the ``AEGIS_DB_URL``
             environment variable, then to :data:`DEFAULT_DSN`.
    
    Returns:
        A synchronous :class:`ConnectionPool`.
    """
    global _sync_pool  # noqa: PLW0603
    
    if _sync_pool is None:
        if dsn is None:
            dsn = os.environ.get("AEGIS_DB_URL", DEFAULT_DSN)
        _sync_pool = ConnectionPool(
            conninfo=dsn,
            min_size=2,
            max_size=10,
            open=True,
        )
    
    return _sync_pool


async def close_pool() -> None:
    """Close the module-level pool if it exists."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None


def close_sync_pool() -> None:
    """Close the synchronous pool if it exists."""
    global _sync_pool  # noqa: PLW0603
    if _sync_pool is not None:
        _sync_pool.close()
        _sync_pool = None
