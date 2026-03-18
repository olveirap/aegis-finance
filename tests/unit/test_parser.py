# SPDX-License-Identifier: MIT
"""Unit tests for Transaction / ImportBatch models and BankCSVParser (Task 1.6)."""

from __future__ import annotations

import csv
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from aegis.parsers.base import (
    BaseParser,
    ImportBatch,
    Transaction,
    VALID_CATEGORIES,
    VALID_CURRENCIES,
)
from aegis.parsers.bank_csv import BankCSVParser, ColumnMapping, _normalise_amount


# ── Constants ────────────────────────────────────────────────────────────────

ACCT = UUID("12345678-1234-5678-1234-567812345678")
SAMPLE_HASH = "a" * 64  # valid 64-char hex string


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_txn(**overrides) -> Transaction:
    """Build a valid Transaction with sensible defaults, merging *overrides*."""
    defaults = {
        "date": date(2026, 1, 15),
        "amount": Decimal("-1500.00"),
        "currency": "ARS",
        "merchant_raw": "CARREFOUR SUC 42",
        "account_id": ACCT,
    }
    defaults.update(overrides)
    return Transaction(**defaults)


def _make_batch(**overrides) -> ImportBatch:
    """Build a valid ImportBatch with sensible defaults."""
    defaults = {
        "account_id": ACCT,
        "file_name": "statement.csv",
        "file_hash": SAMPLE_HASH,
        "row_count": 24,
        "parser_used": "generic_csv",
    }
    defaults.update(overrides)
    return ImportBatch(**defaults)


def _default_mapping(**overrides) -> ColumnMapping:
    """Return a ColumnMapping matching sample_bank.csv layout."""
    defaults = {
        "date_col": "Fecha",
        "amount_col": "Monto",
        "description_col": "Descripción",
        "date_format": "%d/%m/%Y",
        "default_currency": "ARS",
    }
    defaults.update(overrides)
    return ColumnMapping(**defaults)


# ── Transaction Model Tests ──────────────────────────────────────────────────


class TestTransactionModel:
    """Validation of the Transaction Pydantic model."""

    def test_transaction_model_validation(self) -> None:
        """A valid Transaction should be created without errors."""
        txn = _make_txn()
        assert txn.date == date(2026, 1, 15)
        assert txn.amount == Decimal("-1500.00")
        assert txn.currency == "ARS"
        assert txn.account_id == ACCT
        assert txn.is_flagged is False
        assert txn.category_source == "auto"

    def test_transaction_invalid_currency(self) -> None:
        """An unsupported currency code must raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid currency"):
            _make_txn(currency="GBP")

    def test_transaction_invalid_category(self) -> None:
        """An unsupported category must raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid category"):
            _make_txn(category="Shopping")

    def test_transaction_valid_categories(self) -> None:
        """Every category in VALID_CATEGORIES should be accepted."""
        for cat in VALID_CATEGORIES:
            txn = _make_txn(category=cat)
            assert txn.category == cat

    def test_transaction_valid_currencies(self) -> None:
        """Every currency in VALID_CURRENCIES should be accepted."""
        for cur in VALID_CURRENCIES:
            txn = _make_txn(currency=cur)
            assert txn.currency == cur

    def test_transaction_none_category_ok(self) -> None:
        """None category is valid (uncategorized transaction)."""
        txn = _make_txn(category=None)
        assert txn.category is None

    def test_transaction_invalid_category_source(self) -> None:
        """An unsupported category_source must raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid category_source"):
            _make_txn(category_source="manual")

    def test_transaction_score_bounds(self) -> None:
        """category_score must be between 0.0 and 1.0."""
        txn = _make_txn(category_score=0.0)
        assert txn.category_score == 0.0
        txn = _make_txn(category_score=1.0)
        assert txn.category_score == 1.0
        with pytest.raises(ValidationError):
            _make_txn(category_score=1.5)
        with pytest.raises(ValidationError):
            _make_txn(category_score=-0.1)


# ── ImportBatch Model Tests ──────────────────────────────────────────────────


class TestImportBatchModel:
    """Validation of the ImportBatch Pydantic model."""

    def test_import_batch_model(self) -> None:
        """A valid ImportBatch should be created without errors."""
        batch = _make_batch()
        assert batch.file_name == "statement.csv"
        assert batch.row_count == 24
        assert batch.status == "completed"

    def test_import_batch_invalid_hash_length_short(self) -> None:
        """A hash shorter than 64 chars must raise ValidationError."""
        with pytest.raises(ValidationError):
            _make_batch(file_hash="abc123")

    def test_import_batch_invalid_hash_length_long(self) -> None:
        """A hash longer than 64 chars must raise ValidationError."""
        with pytest.raises(ValidationError):
            _make_batch(file_hash="a" * 65)

    def test_import_batch_invalid_status(self) -> None:
        """An unsupported status must raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid status"):
            _make_batch(status="cancelled")

    def test_import_batch_valid_statuses(self) -> None:
        """All valid statuses should be accepted."""
        for s in ("pending", "processing", "completed", "failed"):
            batch = _make_batch(status=s)
            assert batch.status == s


# ── compute_file_hash ────────────────────────────────────────────────────────


class TestComputeFileHash:
    """BaseParser.compute_file_hash static method."""

    def test_compute_file_hash(self, sample_csv_path: Path) -> None:
        """Hash of sample CSV must be a 64-char lowercase hex string."""
        h = BaseParser.compute_file_hash(sample_csv_path)
        assert len(h) == 64
        assert h == h.lower()
        # Validate it's actual hex
        int(h, 16)

    def test_hash_is_deterministic(self, sample_csv_path: Path) -> None:
        """Hashing the same file twice must yield the same result."""
        h1 = BaseParser.compute_file_hash(sample_csv_path)
        h2 = BaseParser.compute_file_hash(sample_csv_path)
        assert h1 == h2

    def test_hash_matches_stdlib(self, sample_csv_path: Path) -> None:
        """Result must match a plain hashlib.sha256 read of the same file."""
        expected = hashlib.sha256(sample_csv_path.read_bytes()).hexdigest()
        assert BaseParser.compute_file_hash(sample_csv_path) == expected


# ── BankCSVParser ────────────────────────────────────────────────────────────


class TestBankCSVParser:
    """Parsing CSV files with BankCSVParser."""

    def test_parse_sample_csv(self, sample_csv_path: Path) -> None:
        """sample_bank.csv has 24 data rows; all should parse successfully."""
        parser = BankCSVParser(
            mapping=_default_mapping(),
            account_id=ACCT,
        )
        txns = parser.parse(sample_csv_path)
        assert len(txns) == 24
        # First row: SUELDO EMPRESA TECH SA, positive
        assert txns[0].amount == Decimal("950000.00")
        assert txns[0].date == date(2026, 1, 1)
        # Second row: CARREFOUR, negative
        assert txns[1].amount == Decimal("-23450.50")

    def test_parse_column_mapping(self, sample_csv_path: Path) -> None:
        """Configured column names must be used by the parser."""
        mapping = _default_mapping()
        parser = BankCSVParser(mapping=mapping, account_id=ACCT)
        txns = parser.parse(sample_csv_path)
        # merchant_raw should come from the description_col (Descripción)
        # because no merchant_col is specified
        assert txns[0].merchant_raw == "SUELDO EMPRESA TECH SA"
        assert txns[0].currency == "ARS"

    def test_all_transactions_have_account_id(self, sample_csv_path: Path) -> None:
        """Every parsed transaction must carry the configured account_id."""
        parser = BankCSVParser(mapping=_default_mapping(), account_id=ACCT)
        for txn in parser.parse(sample_csv_path):
            assert txn.account_id == ACCT


class TestAmountNormalisation:
    """_normalise_amount helper handles diverse number formats."""

    def test_argentine_format(self) -> None:
        """'1.234,56' → 1234.56 (Argentine thousands/decimal)."""
        assert _normalise_amount("1.234,56") == Decimal("1234.56")

    def test_argentine_large(self) -> None:
        """'1.234.567,89' → 1234567.89."""
        assert _normalise_amount("1.234.567,89") == Decimal("1234567.89")

    def test_negative_argentine(self) -> None:
        """'-23.450,50' → -23450.50."""
        assert _normalise_amount("-23.450,50") == Decimal("-23450.50")

    def test_international_format(self) -> None:
        """'1,234.56' → 1234.56."""
        assert _normalise_amount("1,234.56") == Decimal("1234.56")

    def test_plain_decimal(self) -> None:
        """'1234.56' → 1234.56."""
        assert _normalise_amount("1234.56") == Decimal("1234.56")

    def test_plain_integer(self) -> None:
        """'-1234' → -1234."""
        assert _normalise_amount("-1234") == Decimal("-1234")

    def test_currency_symbol_stripped(self) -> None:
        """'$23.450,50' → 23450.50 (symbol removed)."""
        assert _normalise_amount("$23.450,50") == Decimal("23450.50")

    def test_empty_string_raises(self) -> None:
        """Empty or whitespace-only input must raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            _normalise_amount("   ")


class TestCSVEdgeCases:
    """Edge cases: encoding fallback, malformed rows, empty files."""

    def test_encoding_fallback(self, tmp_path: Path) -> None:
        """Latin-1 encoded content should be decoded via fallback."""
        content = "Fecha,Descripción,Monto\n01/01/2026,CAFÉ MARTÍNEZ,-2150.00\n"
        p = tmp_path / "latin1.csv"
        p.write_bytes(content.encode("latin-1"))

        parser = BankCSVParser(
            mapping=_default_mapping(),
            account_id=ACCT,
        )
        txns = parser.parse(p)
        assert len(txns) == 1
        assert txns[0].amount == Decimal("-2150.00")

    def test_malformed_rows_skipped(self, tmp_path: Path) -> None:
        """Rows with bad dates or amounts are skipped (not crashing)."""
        lines = [
            "Fecha,Descripción,Monto",
            "01/01/2026,GOOD ROW,-100.00",        # valid
            "BADDATE,BAD ROW,-200.00",             # invalid date
            "02/01/2026,MISSING AMOUNT,",          # empty amount
            "03/01/2026,ANOTHER GOOD,-300.00",     # valid
        ]
        p = tmp_path / "bad.csv"
        p.write_text("\n".join(lines), encoding="utf-8")

        parser = BankCSVParser(mapping=_default_mapping(), account_id=ACCT)
        txns = parser.parse(p)
        assert len(txns) == 2
        assert txns[0].amount == Decimal("-100.00")
        assert txns[1].amount == Decimal("-300.00")

    def test_empty_csv(self, tmp_path: Path) -> None:
        """Parsing a CSV with headers only returns an empty list."""
        p = tmp_path / "empty.csv"
        p.write_text("Fecha,Descripción,Monto\n", encoding="utf-8")

        parser = BankCSVParser(mapping=_default_mapping(), account_id=ACCT)
        txns = parser.parse(p)
        assert txns == []

    def test_completely_empty_file(self, tmp_path: Path) -> None:
        """A completely empty file returns an empty list."""
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")

        parser = BankCSVParser(mapping=_default_mapping(), account_id=ACCT)
        txns = parser.parse(p)
        assert txns == []

    def test_skip_rows(self, tmp_path: Path) -> None:
        """skip_rows setting should skip leading meta-data lines."""
        lines = [
            "Bank Export v2.0",                       # meta row
            "Fecha,Descripción,Monto",                # header
            "01/01/2026,SOME MERCHANT,-500.00",
        ]
        p = tmp_path / "skip.csv"
        p.write_text("\n".join(lines), encoding="utf-8")

        mapping = _default_mapping(skip_rows=1)
        parser = BankCSVParser(mapping=mapping, account_id=ACCT)
        txns = parser.parse(p)
        assert len(txns) == 1
        assert txns[0].amount == Decimal("-500.00")
