import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from aegis.parsers.base import BaseParser, Transaction
from aegis.parsers.bank_csv import (
    _read_csv_with_fallback,
    _clean_merchant,
    _resolve_column,
)
from aegis.parsers.utils import clean_amount as utils_clean_amount

logger = logging.getLogger(__name__)


class ICBCParser(BaseParser):
    """
    ICBC-specific CSV parser.
    Handles the separated Debit/Credit columns and auto-detects the header row.
    """

    def __init__(
        self,
        account_id: UUID,
        date_col: str = "Fecha",
        debit_col: str = "Débito",
        credit_col: str = "Crédito",
        desc_col: str = "Concepto",
    ):
        self.account_id = account_id
        self.date_col = date_col
        self.debit_col = debit_col
        self.credit_col = credit_col
        self.desc_col = desc_col
        self.parser_name = "icbc"

    @staticmethod
    def clean_amount(raw: str) -> Decimal:
        return utils_clean_amount(raw)

    def parse(self, file_path: Path) -> list[Transaction]:
        # 1. Detect header row by scanning lines for expected columns
        # Expected column count or specific header names. Let's look for our target columns.
        skip_rows = 0

        # Read lines with fallback
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                lines = file_path.read_text(encoding=enc).splitlines()
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            raise ValueError(
                f"Could not decode {file_path} with any attempted encoding."
            )

        for i, line in enumerate(lines):
            # A simplistic check: if it contains Date and Debit/Credit columns
            # usually ICBC has specific exact words.
            if (
                self.date_col in line
                and self.debit_col in line
                and self.credit_col in line
            ):
                skip_rows = i
                break

        # 2. Use _read_csv_with_fallback
        rows = _read_csv_with_fallback(
            file_path,
            encoding="utf-8",  # fallback mechanism handles this inside _read_csv_with_fallback
            delimiter=",",
            skip_rows=skip_rows,
        )

        transactions: list[Transaction] = []
        for row_num, row in enumerate(rows, start=skip_rows + 2):
            try:
                txn = self._parse_row(row, row_num)
                if txn:
                    transactions.append(txn)
            except Exception:
                logger.warning(
                    "Skipping row %d in %s: failed to parse",
                    row_num,
                    file_path.name,
                    exc_info=True,
                )

        logger.info(
            "Parsed %d rows from %s",
            len(transactions),
            file_path.name,
        )
        return transactions

    def _parse_row(self, row: dict[str, str], row_num: int) -> Transaction | None:
        raw_date = _resolve_column(row, self.date_col)
        if not raw_date or not raw_date.strip():
            raise ValueError(f"Row {row_num}: missing date")

        # ICBC dates are typically dd/mm/yyyy
        parsed_date = datetime.strptime(raw_date.strip(), "%d/%m/%Y").date()

        raw_debit = _resolve_column(row, self.debit_col) or "0"
        raw_credit = _resolve_column(row, self.credit_col) or "0"

        # If both are empty/invalid, clean_amount might fail, but let's handle "0" or empty
        if not raw_debit.strip():
            raw_debit = "0"
        if not raw_credit.strip():
            raw_credit = "0"

        debit = self.clean_amount(raw_debit)
        credit = self.clean_amount(raw_credit)

        amount = credit - debit
        # If both are 0, maybe skip? We'll let it be parsed, often fees might be 0 but usually we skip if it's empty

        desc_raw = _resolve_column(row, self.desc_col)
        merchant_clean = _clean_merchant(desc_raw)

        return Transaction(
            date=parsed_date,
            amount=amount,
            currency="ARS",  # Default for ICBC
            merchant_raw=desc_raw.strip() if desc_raw else None,
            merchant_clean=merchant_clean,
            description=None,
            account_id=self.account_id,
        )
