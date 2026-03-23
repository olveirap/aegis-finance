import logging
import csv
import io
from datetime import datetime
from pathlib import Path
from uuid import UUID

from aegis.parsers.base import BaseParser, Transaction
from aegis.parsers.bank_csv import _clean_merchant, _resolve_column
from aegis.parsers.utils import clean_amount

logger = logging.getLogger(__name__)


class MercadoPagoParser(BaseParser):
    """
    MercadoPago activity export parser.
    Handles semicolon-delimited CSVs with embedded metadata headers.
    """

    def __init__(self, account_id: UUID):
        self.account_id = account_id
        self.parser_name = "mercadopago"

        # Fixed mapping
        self.date_col = "RELEASE_DATE"
        self.desc_col = "TRANSACTION_TYPE"
        self.amount_col = "TRANSACTION_NET_AMOUNT"

    def parse(self, file_path: Path) -> list[Transaction]:
        # Read lines with fallback
        text = ""
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                text = file_path.read_text(encoding=enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            raise ValueError(
                f"Could not decode {file_path} with any attempted encoding."
            )

        lines = text.splitlines()

        # Find the header row
        skip_rows = -1
        for i, line in enumerate(lines):
            if self.date_col in line:
                skip_rows = i
                break

        if skip_rows == -1:
            logger.warning(
                "No %r header found in %s. Returning empty list.",
                self.date_col,
                file_path.name,
            )
            return []

        reader_input = io.StringIO(text)
        for _ in range(skip_rows):
            next(reader_input, None)

        reader = csv.DictReader(reader_input, delimiter=";")
        rows = list(reader)

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

        # MP dates are typically dd/mm/yyyy or yyyy-mm-dd. Let's try dd/mm/yyyy based on the test
        try:
            parsed_date = datetime.strptime(raw_date.strip(), "%d/%m/%Y").date()
        except ValueError:
            try:
                parsed_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                # Let pydantic or other code fail if it's completely unknown
                raise ValueError(f"Row {row_num}: could not parse date {raw_date!r}")

        raw_amount = _resolve_column(row, self.amount_col)
        if not raw_amount or not raw_amount.strip():
            raise ValueError(f"Row {row_num}: missing amount")
        amount = clean_amount(raw_amount)

        desc_raw = _resolve_column(row, self.desc_col)
        merchant_clean = _clean_merchant(desc_raw)

        return Transaction(
            date=parsed_date,
            amount=amount,
            currency="ARS",  # Default for MP
            merchant_raw=desc_raw.strip() if desc_raw else None,
            merchant_clean=merchant_clean,
            description=None,
            account_id=self.account_id,
        )
