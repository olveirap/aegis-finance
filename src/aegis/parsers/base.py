# SPDX-License-Identifier: MIT
"""Abstract parser interface and shared models for statement import.

Defines the :class:`Transaction` and :class:`ImportBatch` Pydantic models
that mirror the database schema, and the :class:`BaseParser` ABC that every
concrete file parser must implement.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

VALID_CURRENCIES = frozenset({"ARS", "USD", "USDT", "EUR"})

VALID_CATEGORIES = frozenset(
    {
        "Housing",
        "Food",
        "Transportation",
        "Entertainment",
        "Health",
        "Education",
        "Utilities",
        "Subscriptions",
        "Work-Expense",
        "Savings",
        "Investment",
        "Transfer",
        "Income",
        "Other",
    }
)

VALID_CATEGORY_SOURCES = frozenset({"auto", "user", "hitl"})

# ── Pydantic Models ─────────────────────────────────────────────────────────


class Transaction(BaseModel):
    """A single financial transaction, matching the ``transactions`` table."""

    model_config = {"frozen": False, "str_strip_whitespace": True}

    date: date
    amount: Decimal = Field(
        ...,
        max_digits=18,
        decimal_places=2,
        description="Negative = expense, positive = income.",
    )
    currency: str = Field(default="ARS", max_length=10)
    merchant_raw: str | None = None
    merchant_clean: str | None = Field(default=None, max_length=200)
    description: str | None = None
    account_id: UUID
    category: str | None = Field(default=None, max_length=50)
    category_score: float | None = Field(default=None, ge=0.0, le=1.0)
    category_source: str = Field(default="auto", max_length=20)
    is_flagged: bool = False

    @model_validator(mode="after")
    def _validate_enums(self) -> Transaction:
        if self.currency not in VALID_CURRENCIES:
            msg = (
                f"Invalid currency {self.currency!r}; "
                f"expected one of {sorted(VALID_CURRENCIES)}"
            )
            raise ValueError(msg)
        if self.category is not None and self.category not in VALID_CATEGORIES:
            msg = (
                f"Invalid category {self.category!r}; "
                f"expected one of {sorted(VALID_CATEGORIES)}"
            )
            raise ValueError(msg)
        if self.category_source not in VALID_CATEGORY_SOURCES:
            msg = (
                f"Invalid category_source {self.category_source!r}; "
                f"expected one of {sorted(VALID_CATEGORY_SOURCES)}"
            )
            raise ValueError(msg)
        return self


class ImportBatch(BaseModel):
    """Metadata for a single file import, matching ``import_batches``."""

    model_config = {"frozen": False, "str_strip_whitespace": True}

    account_id: UUID
    file_name: str = Field(..., max_length=255)
    file_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hex digest of the source file.",
    )
    row_count: int = Field(..., ge=0)
    parser_used: str = Field(..., max_length=50)
    status: str = Field(default="completed", max_length=20)

    @model_validator(mode="after")
    def _validate_status(self) -> ImportBatch:
        valid = {"pending", "processing", "completed", "failed"}
        if self.status not in valid:
            msg = f"Invalid status {self.status!r}; expected one of {sorted(valid)}"
            raise ValueError(msg)
        return self


# ── Abstract Base Parser ────────────────────────────────────────────────────


class BaseParser(ABC):
    """ABC that every statement parser must subclass."""

    @abstractmethod
    def parse(self, file_path: Path) -> list[Transaction]:
        """Parse a file and return a list of validated transactions.

        Args:
            file_path: Path to the statement file to parse.

        Returns:
            A list of :class:`Transaction` objects.
        """

    # ── Concrete helpers ────────────────────────────────────────────────

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute the SHA-256 hex digest of *file_path*.

        Reads the file in 64 KiB chunks to avoid loading large files into
        memory all at once.

        Args:
            file_path: Path to the file to hash.

        Returns:
            Lowercase hex-encoded SHA-256 digest (64 characters).
        """
        sha = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65_536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    async def persist(
        self,
        transactions: list[Transaction],
        batch: ImportBatch,
        conn: AsyncConnection,
    ) -> int:
        """Insert an import batch and its transactions into the database.

        The method operates inside the caller-provided connection.  It creates
        a savepoint for each individual transaction row so that a duplicate-key
        violation on one row does not abort the entire batch.

        Args:
            transactions: Validated :class:`Transaction` objects to insert.
            batch: The :class:`ImportBatch` metadata for the import.
            conn: An open :class:`psycopg.AsyncConnection`.

        Returns:
            The number of transaction rows successfully inserted (duplicates
            are silently skipped and logged as warnings).
        """
        # -- 1. Insert the batch row and retrieve the generated UUID ------
        row = await conn.execute(
            """
            INSERT INTO import_batches
                   (account_id, file_name, file_hash, row_count,
                    parser_used, status)
            VALUES (%(account_id)s, %(file_name)s, %(file_hash)s,
                    %(row_count)s, %(parser_used)s, %(status)s)
            RETURNING id
            """,
            {
                "account_id": str(batch.account_id),
                "file_name": batch.file_name,
                "file_hash": batch.file_hash,
                "row_count": batch.row_count,
                "parser_used": batch.parser_used,
                "status": batch.status,
            },
        )
        batch_id = (await row.fetchone())[0]  # type: ignore[index]
        logger.info(
            "Created import_batch %s (%s, %d rows)",
            batch_id,
            batch.file_name,
            batch.row_count,
        )

        # -- 2. Insert each transaction, skipping duplicates --------------
        inserted = 0
        duplicates = 0

        insert_sql = """
            INSERT INTO transactions
                   (account_id, date, amount, currency,
                    merchant_raw, merchant_clean, description,
                    category, category_score, category_source,
                    is_flagged, import_batch_id)
            VALUES (%(account_id)s, %(date)s, %(amount)s, %(currency)s,
                    %(merchant_raw)s, %(merchant_clean)s, %(description)s,
                    %(category)s, %(category_score)s, %(category_source)s,
                    %(is_flagged)s, %(import_batch_id)s)
        """

        for idx, txn in enumerate(transactions):
            params = {
                "account_id": str(txn.account_id),
                "date": txn.date,
                "amount": txn.amount,
                "currency": txn.currency,
                "merchant_raw": txn.merchant_raw,
                "merchant_clean": txn.merchant_clean,
                "description": txn.description,
                "category": txn.category,
                "category_score": (
                    Decimal(str(txn.category_score))
                    if txn.category_score is not None
                    else None
                ),
                "category_source": txn.category_source,
                "is_flagged": txn.is_flagged,
                "import_batch_id": str(batch_id),
            }
            try:
                async with conn.transaction():
                    await conn.execute(insert_sql, params)
                inserted += 1
            except UniqueViolation:
                duplicates += 1
                logger.warning(
                    "Duplicate transaction skipped (row %d): "
                    "date=%s amount=%s merchant_raw=%r",
                    idx,
                    txn.date,
                    txn.amount,
                    txn.merchant_raw,
                )

        logger.info(
            "Batch %s: inserted=%d, duplicates=%d, total=%d",
            batch_id,
            inserted,
            duplicates,
            len(transactions),
        )

        return inserted
