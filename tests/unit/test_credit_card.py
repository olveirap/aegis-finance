from uuid import uuid4
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from aegis.parsers.credit_card import CreditCardParser


def test_credit_card_parse_lines():
    # We will test the regex line parser directly.
    account_id = uuid4()
    parser = CreditCardParser(account_id=account_id, card_brand="visa")

    lines = [
        "15.01.24 COMPRA EN SUPER 1.500,00 0,00",  # Standard ARS line
        "16/01/2024 AMAZON USD 0,00 50,00",  # Non-zero USD column
        "17-01-2024 IVA RG 4240 21%(103887,00) 21.816,27 0,00",  # Tax line
        "18.01.24 DEVOLUCION 35.771,17- 0,00",  # Trailing-minus negative amount
        "19.01.24 HOTEL EUR 0,00 120,50",  # EUR descriptor line -> mapped to USD
        "20.01.24 VUELOS 1.234.567,89 0,00",  # Thousands dots
        "Not a date line",
        "21.01.24 NO AMOUNT HERE",
    ]

    transactions = parser._parse_lines(lines)

    assert len(transactions) == 6

    # Standard ARS line
    assert transactions[0].date == date(2024, 1, 15)
    assert transactions[0].amount == Decimal("-1500.00")
    assert transactions[0].currency == "ARS"
    assert "COMPRA EN SUPER" in transactions[0].merchant_raw

    # Non-zero USD column
    assert transactions[1].date == date(2024, 1, 16)
    assert transactions[1].amount == Decimal("-50.00")
    assert transactions[1].currency == "USD"
    assert "AMAZON" in transactions[1].merchant_raw

    # Tax line
    assert transactions[2].date == date(2024, 1, 17)
    assert transactions[2].amount == Decimal("-21816.27")
    assert transactions[2].currency == "ARS"
    assert "IVA RG 4240" in transactions[2].merchant_raw

    # Trailing minus (credit/reversal) -> positive amount
    assert transactions[3].date == date(2024, 1, 18)
    assert transactions[3].amount == Decimal("35771.17")

    # EUR descriptor -> mapped to USD
    assert transactions[4].date == date(2024, 1, 19)
    assert transactions[4].amount == Decimal("-120.50")
    assert transactions[4].currency == "USD"

    # Thousands dots
    assert transactions[5].date == date(2024, 1, 20)
    assert transactions[5].amount == Decimal("-1234567.89")


@patch("aegis.parsers.credit_card.pdfplumber.open")
def test_credit_card_parse_file(mock_open, tmp_path):
    # Setup mock
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = (
        "15.01.24 COMPRA EN SUPER 1.500,00 0,00\n16/01/2024 AMAZON USD 0,00 50,00"
    )
    mock_pdf.pages = [mock_page]
    mock_open.return_value.__enter__.return_value = mock_pdf

    file_path = tmp_path / "statement.pdf"
    file_path.write_text("dummy", encoding="utf-8")

    account_id = uuid4()
    parser = CreditCardParser(account_id=account_id, card_brand="mastercard")
    transactions = parser.parse(file_path)

    assert len(transactions) == 2
    assert transactions[0].currency == "ARS"
    assert transactions[1].currency == "USD"
    assert transactions[0].amount == Decimal("-1500.00")
    assert transactions[1].amount == Decimal("-50.00")
