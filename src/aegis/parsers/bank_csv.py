# SPDX-License-Identifier: MIT
"""Generic bank CSV parser with configurable column mapping.

Handles Argentine bank statements (encoding quirks, date formats,
number formatting with period-thousands / comma-decimal) as well as
international CSV exports.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field

from aegis.parsers.base import BaseParser, Transaction

logger = logging.getLogger(__name__)

# ── Column Mapping Configuration ────────────────────────────────────────────


class ColumnMapping(BaseModel):
    """Describes how CSV columns map to :class:`Transaction` fields."""

    model_config = {"frozen": False, "str_strip_whitespace": True}

    date_col: str = Field(
        ..., description="Column name (or 0-based index as string) for the date."
    )
    amount_col: str = Field(
        ..., description="Column name (or 0-based index as string) for the amount."
    )
    merchant_col: str | None = Field(
        default=None,
        description="Column name for merchant / payee.  Falls back to description.",
    )
    description_col: str | None = Field(
        default=None, description="Column name for an auxiliary description field."
    )
    currency_col: str | None = Field(
        default=None,
        description=(
            "Column name for per-row currency.  "
            "When absent, *default_currency* is used for every row."
        ),
    )
    date_format: str = Field(
        default="%d/%m/%Y",
        description="strptime format string (Argentine default: dd/mm/yyyy).",
    )
    default_currency: str = "ARS"
    delimiter: str = ","
    encoding: str = "utf-8"
    skip_rows: int = Field(
        default=0,
        ge=0,
        description="Number of header/meta rows to skip before the actual header.",
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

# Regex that matches common currency symbols / codes prepended or appended
_CURRENCY_SYMBOL_RE = re.compile(
    r"[ARS$U€\s]+",  # loose strip of $, AR$, US$, €, whitespace
)

# Argentine thousands separator: 1.234.567,89
# International format:          1,234,567.89
_ARGENTINE_NUMBER_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$")


def _normalise_amount(raw: str) -> Decimal:
    """Parse a human-formatted amount string into a :class:`Decimal`.

    Handles:
    * ``-$23.450,50``  → ``-23450.50``  (Argentine)
    * ``1,234.56``     → ``1234.56``    (International)
    * ``1234.56``      → ``1234.56``    (Plain)
    * ``-1234``        → ``-1234``

    Raises:
        ValueError: If the string cannot be converted to a valid number.
    """
    # Strip any currency symbols, letters, and stray whitespace
    cleaned = re.sub(r"[^\d.,-]", "", raw.strip())
    if not cleaned:
        msg = f"Cannot parse amount from empty/non-numeric value: {raw!r}"
        raise ValueError(msg)

    # Detect Argentine format: uses '.' as thousands sep and ',' as decimal
    if _ARGENTINE_NUMBER_RE.match(cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")

    # International format: strip thousands commas, keep decimal dot
    elif "," in cleaned and "." in cleaned:
        # e.g. "1,234.56" — comma before dot → comma is thousands
        last_comma = cleaned.rfind(",")
        last_dot = cleaned.rfind(".")
        if last_dot > last_comma:
            cleaned = cleaned.replace(",", "")
        else:
            # e.g. "1.234,56" — dot before comma → dot is thousands
            cleaned = cleaned.replace(".", "").replace(",", ".")

    elif "," in cleaned:
        # Single comma, no dot — could be decimal separator
        # Heuristic: if exactly 1-2 digits after the comma, treat as decimal
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            # Thousands separator only (e.g. "1,234")
            cleaned = cleaned.replace(",", "")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        msg = f"Cannot convert {raw!r} (cleaned: {cleaned!r}) to Decimal"
        raise ValueError(msg) from exc


def _clean_merchant(raw: str | None) -> str | None:
    """Normalise a merchant name: strip, collapse whitespace, title-case."""
    if raw is None:
        return None
    cleaned = " ".join(raw.split())  # collapse whitespace
    if not cleaned:
        return None
    return cleaned.strip()


def _read_csv_with_fallback(
    file_path: Path,
    encoding: str,
    delimiter: str,
    skip_rows: int,
) -> list[dict[str, str]]:
    """Read a CSV file, trying *encoding* first and falling back to latin-1.

    Returns a list of row dicts keyed by the header names.
    """
    for enc in _encoding_attempts(encoding):
        try:
            text = file_path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            logger.debug("Encoding %s failed for %s, trying next.", enc, file_path)
    else:
        msg = f"Could not decode {file_path} with any attempted encoding."
        raise ValueError(msg)

    reader_input = io.StringIO(text)

    # Skip leading meta rows
    for _ in range(skip_rows):
        next(reader_input, None)

    reader = csv.DictReader(reader_input, delimiter=delimiter)
    return list(reader)


def _encoding_attempts(primary: str) -> list[str]:
    """Return a deduplicated ordered list of encodings to attempt."""
    candidates: list[str] = [primary]
    if primary.lower().replace("-", "") != "latin1":
        candidates.append("latin-1")
    if primary.lower().replace("-", "") != "cp1252":
        candidates.append("cp1252")
    return candidates


def _resolve_column(row: dict[str, str], col_spec: str) -> str | None:
    """Retrieve a value from *row* by column name or numeric index.

    If *col_spec* is a digit string (e.g. ``"2"``), it is treated as a
    0-based positional index into ``row.values()``.
    """
    if col_spec in row:
        return row[col_spec]

    # Try as numeric index
    if col_spec.isdigit():
        idx = int(col_spec)
        values = list(row.values())
        if 0 <= idx < len(values):
            return values[idx]

    return None


# ── BankCSVParser ───────────────────────────────────────────────────────────


class BankCSVParser(BaseParser):
    """Configurable CSV parser for bank/credit-card statements.

    Args:
        mapping: A :class:`ColumnMapping` describing the CSV layout.
        account_id: UUID of the target account in the ``accounts`` table.
        parser_name: Identifier stored in ``import_batches.parser_used``.
    """

    def __init__(
        self,
        mapping: ColumnMapping,
        account_id: UUID,
        parser_name: str = "generic_csv",
    ) -> None:
        self.mapping = mapping
        self.account_id = account_id
        self.parser_name = parser_name

    # ── BaseParser implementation ───────────────────────────────────────

    def parse(self, file_path: Path) -> list[Transaction]:
        """Parse a CSV file and return validated transactions.

        Rows that fail validation are skipped with a warning log.

        Args:
            file_path: Path to the CSV file.

        Returns:
            A list of :class:`Transaction` objects.
        """
        rows = _read_csv_with_fallback(
            file_path,
            encoding=self.mapping.encoding,
            delimiter=self.mapping.delimiter,
            skip_rows=self.mapping.skip_rows,
        )

        transactions: list[Transaction] = []
        for row_num, row in enumerate(rows, start=1):
            try:
                txn = self._parse_row(row, row_num)
                transactions.append(txn)
            except Exception:
                logger.warning(
                    "Skipping row %d in %s: failed to parse",
                    row_num,
                    file_path.name,
                    exc_info=True,
                )

        logger.info(
            "Parsed %d/%d rows from %s",
            len(transactions),
            len(rows),
            file_path.name,
        )
        return transactions

    # ── Internal helpers ────────────────────────────────────────────────

    def _parse_row(self, row: dict[str, str], row_num: int) -> Transaction:
        """Convert a single CSV row dict into a :class:`Transaction`."""
        m = self.mapping

        # -- Date --
        raw_date = _resolve_column(row, m.date_col)
        if raw_date is None or not raw_date.strip():
            msg = f"Row {row_num}: missing date in column {m.date_col!r}"
            raise ValueError(msg)
        parsed_date = datetime.strptime(raw_date.strip(), m.date_format).date()

        # -- Amount --
        raw_amount = _resolve_column(row, m.amount_col)
        if raw_amount is None or not raw_amount.strip():
            msg = f"Row {row_num}: missing amount in column {m.amount_col!r}"
            raise ValueError(msg)
        amount = _normalise_amount(raw_amount)

        # -- Currency --
        currency = m.default_currency
        if m.currency_col is not None:
            raw_cur = _resolve_column(row, m.currency_col)
            if raw_cur and raw_cur.strip():
                currency = raw_cur.strip().upper()

        # -- Merchant / Description --
        merchant_raw: str | None = None
        if m.merchant_col is not None:
            merchant_raw = _resolve_column(row, m.merchant_col)

        description: str | None = None
        if m.description_col is not None:
            description = _resolve_column(row, m.description_col)

        # If no explicit merchant column, use the description column value
        if merchant_raw is None and description is not None:
            merchant_raw = description

        merchant_clean = _clean_merchant(merchant_raw)

        return Transaction(
            date=parsed_date,
            amount=amount,
            currency=currency,
            merchant_raw=merchant_raw.strip() if merchant_raw else None,
            merchant_clean=merchant_clean,
            description=description.strip() if description else None,
            account_id=self.account_id,
        )
