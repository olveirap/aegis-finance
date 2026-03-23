import logging
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

import pdfplumber

from aegis.parsers.base import BaseParser, Transaction
from aegis.parsers.bank_csv import _clean_merchant
from aegis.parsers.utils import clean_amount

logger = logging.getLogger(__name__)


class CreditCardParser(BaseParser):
    """
    Parser for Argentine credit card PDFs (Visa, Mastercard) via text extraction and regex.
    """

    def __init__(self, account_id: UUID, card_brand: Literal["visa", "mastercard"]):
        self.account_id = account_id
        self.parser_name = card_brand
        self.card_brand = card_brand

        # Regex anchored to a date pattern at line start: e.g. 15.01.24 or 15/01/2024
        self.line_matcher = re.compile(r"^(\d{2}[./-]\d{2}[./-]\d{2,4})\s+(.+)$")
        # Match tokens at end of line like 1.500,00 or 0,00 or 35.771,17-
        self.amount_tokens_matcher = re.compile(
            r"((?:-?[\d.]+,[\d]{2}-?)\s+(?:-?[\d.]+,[\d]{2}-?))$"
        )

    def parse(self, file_path: Path) -> list[Transaction]:
        lines = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if not text:
                        logger.warning(
                            "Empty text extracted from page %d of %s",
                            i + 1,
                            file_path.name,
                        )
                        continue
                    lines.extend(text.splitlines())
        except Exception:
            logger.warning("Failed to read PDF %s", file_path.name, exc_info=True)
            return []

        transactions = self._parse_lines(lines)
        logger.info("Parsed %d transactions from %s", len(transactions), file_path.name)
        return transactions

    def _parse_lines(self, lines: list[str]) -> list[Transaction]:
        transactions = []
        for row_num, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue

            match = self.line_matcher.match(line)
            if not match:
                continue

            raw_date = match.group(1)
            rest_of_line = match.group(2)

            amount_match = self.amount_tokens_matcher.search(rest_of_line)
            if not amount_match:
                continue

            amounts_str = amount_match.group(1)
            description = rest_of_line[: amount_match.start()].strip()

            amount_tokens = amounts_str.split()
            if len(amount_tokens) != 2:
                continue

            penultimate_token, last_token = amount_tokens

            try:
                # Credit card statements: expenses are positive in PDF, but we want them as negative
                # Credits/payments are negative in PDF (with trailing minus), so we want them positive
                # clean_amount will return positive for 1.500,00 and negative for 35.771,17-
                # So we just multiply the result of clean_amount by -1.

                penultimate_val = clean_amount(penultimate_token) * Decimal("-1")
                last_val = clean_amount(last_token) * Decimal("-1")
            except ValueError:
                logger.warning("Failed to parse amount on line %d: %s", row_num, line)
                continue

            if last_val != Decimal("0.00"):
                amount = last_val
                # If there's a USD amount, currency is USD
                currency = "USD"
            else:
                amount = penultimate_val
                # If EUR is in description, treat as USD (often converted or billed that way)
                if re.search(r"\b(USD|U\$S|EUR)\b", description, re.IGNORECASE):
                    currency = "USD"
                else:
                    currency = "ARS"

            # Date parsing
            raw_date_clean = raw_date.replace(".", "/").replace("-", "/")
            try:
                if len(raw_date_clean.split("/")[-1]) == 2:
                    parsed_date = datetime.strptime(raw_date_clean, "%d/%m/%y").date()
                else:
                    parsed_date = datetime.strptime(raw_date_clean, "%d/%m/%Y").date()
            except ValueError:
                logger.warning("Failed to parse date on line %d: %s", row_num, raw_date)
                continue

            merchant_clean = _clean_merchant(description)

            transactions.append(
                Transaction(
                    date=parsed_date,
                    amount=amount,
                    currency=currency,
                    merchant_raw=description,
                    merchant_clean=merchant_clean,
                    description=None,
                    account_id=self.account_id,
                )
            )

        return transactions
