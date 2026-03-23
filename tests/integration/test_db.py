# SPDX-License-Identifier: MIT
"""Integration tests for the async PostgreSQL connection pool (Task 1.6).

All tests in this file require a running PostgreSQL instance (typically via
Docker) and are marked with ``@pytest.mark.integration`` so they can be
excluded from CI or local runs that lack a database.

Run only integration tests:
    pytest -m integration
Skip them:
    pytest -m "not integration"
"""

from __future__ import annotations

import pytest
import pytest_asyncio

# Guard against missing psycopg_pool (not installed outside Docker env).
try:
    from aegis.db.connection import (
        check_health,
        close_pool,
        get_pool,
    )

    _HAS_DB_DEPS = True
except ImportError:
    _HAS_DB_DEPS = False

# ── Markers ──────────────────────────────────────────────────────────────────

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not _HAS_DB_DEPS, reason="psycopg_pool not installed"),
]


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def pool():
    """Yield a connection pool and tear it down afterwards."""
    p = await get_pool()
    yield p
    await close_pool()


# ── Expected schema objects ──────────────────────────────────────────────────

EXPECTED_TABLES = {
    "accounts",
    "transactions",
    "import_batches",
    "assets",
    "income_sources",
    "exchange_rates",
    "kb_chunks",
    "kb_entities",
    "kb_relations",
    "ingestion_state",
}

EXPECTED_VIEWS = {
    "v_net_worth",
    "v_monthly_burn",
    "v_cedear_exposure",
    "v_income_summary",
    "v_category_spend",
}


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPoolLifecycle:
    """Connection pool creation and health checks."""

    async def test_pool_creation(self, pool) -> None:
        """get_pool must create a pool without error."""
        assert pool is not None

    async def test_health_check(self, pool) -> None:
        """check_health should return True on a reachable database."""
        result = await check_health(pool)
        assert result is True

    async def test_get_connection(self, pool) -> None:
        """get_connection should yield a working connection."""
        async with pool.connection() as conn:
            cur = await conn.execute("SELECT 1 AS n")
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 1


class TestSchemaObjects:
    """Verify the database schema contains the expected tables and views."""

    async def test_tables_exist(self, pool) -> None:
        """All 10 expected tables must exist in the public schema."""
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT table_name
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_type   = 'BASE TABLE'
                """
            )
            rows = await cur.fetchall()
            table_names = {r[0] for r in rows}

        missing = EXPECTED_TABLES - table_names
        assert not missing, f"Missing tables: {missing}"

    async def test_views_exist(self, pool) -> None:
        """All 5 expected views must exist in the public schema."""
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT table_name
                  FROM information_schema.views
                 WHERE table_schema = 'public'
                """
            )
            rows = await cur.fetchall()
            view_names = {r[0] for r in rows}

        missing = EXPECTED_VIEWS - view_names
        assert not missing, f"Missing views: {missing}"
