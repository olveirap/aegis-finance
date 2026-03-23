import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import date

from aegis.parsers.icbc import ICBCParser


def test_icbc_parser_clean_amount():
    # Regular amounts
    assert ICBCParser.clean_amount("1.234,56") == Decimal("1234.56")
    assert ICBCParser.clean_amount("12,34") == Decimal("12.34")
    # Trailing minus
    assert ICBCParser.clean_amount("35.771,17-") == Decimal("-35771.17")
    # Leading minus
    assert ICBCParser.clean_amount("-100,50") == Decimal("-100.50")
    # Empty
    with pytest.raises(ValueError):
        ICBCParser.clean_amount("")


def test_icbc_parse_file(tmp_path):
    # Create a fixture file
    csv_content = """Some header info
More meta info
Fecha,Concepto,Referencia,Débito,Crédito,Saldo
01/01/2023,COMPRA EN SUPER,-,"1.500,00","0,00","10.000,00"
02/01/2023,SUELDO,-,"0,00","50.000,00","60.000,00"
03/01/2023,REVERSO,-,"35.771,17-","0,00","95.771,17"
04/01/2023,INVALIDO,-,foo,bar,baz
"""
    file_path = tmp_path / "icbc_test.csv"
    file_path.write_text(csv_content, encoding="utf-8")

    account_id = uuid4()
    parser = ICBCParser(account_id=account_id)

    transactions = parser.parse(file_path)

    assert len(transactions) == 3

    # Check debits (amount should be negative)
    assert transactions[0].date == date(2023, 1, 1)
    assert transactions[0].amount == Decimal("-1500.00")
    assert transactions[0].merchant_raw == "COMPRA EN SUPER"

    # Check credits (amount should be positive)
    assert transactions[1].date == date(2023, 1, 2)
    assert transactions[1].amount == Decimal("50000.00")
    assert transactions[1].merchant_raw == "SUELDO"

    # Check trailing minus logic inside debit column:
    # A debit of 35.771,17- means a negative debit -> which means credit (returns positive amount)
    assert transactions[2].date == date(2023, 1, 3)
    assert transactions[2].amount == Decimal("35771.17")
