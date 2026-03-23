from uuid import uuid4
from decimal import Decimal
from datetime import date

from aegis.parsers.mercadopago import MercadoPagoParser


def test_mercadopago_parse_file(tmp_path):
    # Create a fixture file
    csv_content = """Some header info
More meta info
Even more info
RELEASE_DATE;TRANSACTION_TYPE;TRANSACTION_NET_AMOUNT;OTHER_COL
01/01/2023;Transferencia;-1.500,00;foo
02/01/2023;Cobro;50.000,00;bar
03/01/2023;Comisión;-35,50;baz
"""
    file_path = tmp_path / "mp_test.csv"
    # MP might use \r\n
    with open(file_path, "w", newline="\r\n", encoding="utf-8") as f:
        f.write(csv_content)

    account_id = uuid4()
    parser = MercadoPagoParser(account_id=account_id)

    transactions = parser.parse(file_path)

    assert len(transactions) == 3

    assert transactions[0].date == date(2023, 1, 1)
    assert transactions[0].amount == Decimal("-1500.00")
    assert transactions[0].merchant_raw == "Transferencia"

    assert transactions[1].date == date(2023, 1, 2)
    assert transactions[1].amount == Decimal("50000.00")
    assert transactions[1].merchant_raw == "Cobro"

    assert transactions[2].date == date(2023, 1, 3)
    assert transactions[2].amount == Decimal("-35.50")
    assert transactions[2].merchant_raw == "Comisión"


def test_mercadopago_no_header(tmp_path):
    csv_content = """No valid header here
Just random data
01/01/2023;Transferencia;-1.500,00;foo
"""
    file_path = tmp_path / "mp_test_bad.csv"
    file_path.write_text(csv_content, encoding="utf-8")

    account_id = uuid4()
    parser = MercadoPagoParser(account_id=account_id)

    transactions = parser.parse(file_path)
    assert len(transactions) == 0
