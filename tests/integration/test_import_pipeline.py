# SPDX-License-Identifier: MIT
"""End-to-end integration test: CSV → parse → categorize → persist (Task 1.6).

Exercises the full import pipeline:
  1. Parse ``sample_bank.csv`` with :class:`BankCSVParser`.
  2. Categorize all transactions with :class:`RuleBasedCategorizer`.
  3. Persist to the database via :meth:`BaseParser.persist`.
  4. Query the database to verify row counts.
  5. Re-import the same file and verify duplicates are rejected.
  6. Verify the ``import_batches`` record exists.

Requires a running PostgreSQL instance — marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio

from aegis.parsers.base import BaseParser, ImportBatch
from aegis.parsers.bank_csv import BankCSVParser, ColumnMapping

# Guard against missing psycopg_pool (not installed outside Docker env).
try:
    from aegis.db.connection import close_pool, get_pool

    _HAS_DB_DEPS = True
except ImportError:
    _HAS_DB_DEPS = False

# Conditionally import categorizer — pipeline test degrades gracefully.
try:
    from aegis.parsers.categorizer import RuleBasedCategorizer

    _HAS_CATEGORIZER = True
except ImportError:
    _HAS_CATEGORIZER = False


# ── Markers ──────────────────────────────────────────────────────────────────

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not _HAS_DB_DEPS, reason="psycopg_pool not installed"),
]

# ── Constants ────────────────────────────────────────────────────────────────

ACCT = UUID("12345678-1234-5678-1234-567812345678")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE_CSV = FIXTURES / "sample_bank.csv"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mapping() -> ColumnMapping:
    return ColumnMapping(
        date_col="Fecha",
        amount_col="Monto",
        description_col="Descripción",
        date_format="%d/%m/%Y",
        default_currency="ARS",
    )


def _make_batch(file_path: Path, row_count: int) -> ImportBatch:
    return ImportBatch(
        account_id=ACCT,
        file_name=file_path.name,
        file_hash=BaseParser.compute_file_hash(file_path),
        row_count=row_count,
        parser_used="generic_csv",
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def pool():
    """Yield a connection pool and tear it down afterwards."""
    p = await get_pool()
    yield p
    await close_pool()


@pytest_asyncio.fixture()
async def clean_db(pool):
    """Delete test data before and after each test to avoid pollution."""
    async with pool.connection() as conn:
        # Ensure account exists to satisfy foreign key constraints
        await conn.execute(
            """
            INSERT INTO accounts (id, name, currency, account_type)
            VALUES (%s, 'Test Account', 'ARS', 'checking')
            ON CONFLICT (id) DO NOTHING
            """,
            (str(ACCT),),
        )
        await conn.execute(
            "DELETE FROM transactions WHERE account_id = %s", (str(ACCT),)
        )
        await conn.execute(
            "DELETE FROM import_batches WHERE account_id = %s", (str(ACCT),)
        )
        await conn.commit()
    yield pool
    # Cleanup after
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM transactions WHERE account_id = %s", (str(ACCT),)
        )
        await conn.execute(
            "DELETE FROM import_batches WHERE account_id = %s", (str(ACCT),)
        )
        await conn.execute("DELETE FROM accounts WHERE id = %s", (str(ACCT),))
        await conn.commit()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestFullPipeline:
    """CSV → parse → categorize → persist → verify."""

    async def test_full_pipeline(self, clean_db) -> None:
        """Run the entire import pipeline and validate DB state."""
        pool = clean_db

        # ── Step 1: Parse ────────────────────────────────────────────────
        parser = BankCSVParser(mapping=_mapping(), account_id=ACCT)
        txns = parser.parse(SAMPLE_CSV)
        assert len(txns) == 24, f"Expected 24 rows, got {len(txns)}"

        # ── Step 2: Categorize (optional — module may not exist yet) ─────
        if _HAS_CATEGORIZER:
            categorizer = RuleBasedCategorizer()
            txns = categorizer.categorize_batch(txns)
            for t in txns:
                assert t.category is not None

        # ── Step 3: Persist ──────────────────────────────────────────────
        batch = _make_batch(SAMPLE_CSV, len(txns))

        async with pool.connection() as conn:
            inserted = await parser.persist(txns, batch, conn)
            await conn.commit()

        assert inserted == 24

        # ── Step 4: Verify row count in DB ───────────────────────────────
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM transactions WHERE account_id = %s",
                (str(ACCT),),
            )
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 24

        # ── Step 5: Re-import same file → duplicates rejected ────────────
        batch2 = ImportBatch(
            account_id=ACCT,
            file_name=SAMPLE_CSV.name,
            file_hash=BaseParser.compute_file_hash(SAMPLE_CSV),
            row_count=len(txns),
            parser_used="generic_csv",
        )

        async with pool.connection() as conn:
            inserted2 = await parser.persist(txns, batch2, conn)
            await conn.commit()

        # All 24 should be duplicates (0 newly inserted)
        assert inserted2 == 0

        # ── Step 6: Verify import_batch records exist ────────────────────
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM import_batches WHERE account_id = %s",
                (str(ACCT),),
            )
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 2  # two batch records (original + re-import)
