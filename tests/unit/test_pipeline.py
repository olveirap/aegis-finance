import pytest

from aegis.parsers.pipeline import run_pipeline
from aegis.parsers.dataframe import EXPECTED_SCHEMA


@pytest.mark.asyncio
async def test_run_pipeline_empty():
    df = await run_pipeline([])
@pytest.mark.asyncio
async def test_run_pipeline_empty():
    df = await run_pipeline([])
    assert len(df) == 0
    assert list(df.columns) == list(EXPECTED_SCHEMA.keys())


@pytest.mark.asyncio
async def test_run_pipeline_integration(tmp_path):
@pytest.mark.asyncio
async def test_run_pipeline_integration(tmp_path):
    # Create fixture files
    icbc_csv = tmp_path / "icbc.csv"
    icbc_csv.write_text(
        """Fecha,Concepto,Referencia,Débito,Crédito,Saldo
01/01/2023,SUPERMERCADO,-,1.500,00,0,00,10.000,00
02/01/2023,PAGO VISA,-,2.000,00,0,00,8.000,00
""",
        encoding="utf-8",
    )

    mp_csv = tmp_path / "mp.csv"
    with open(mp_csv, "w", newline="\r\n", encoding="utf-8") as f:
        f.write("""RELEASE_DATE;TRANSACTION_TYPE;TRANSACTION_NET_AMOUNT;OTHER
03/01/2023;Transferencia a Juan;-500,00;foo
""")

    sources = [
        {"type": "icbc", "path": icbc_csv},
        {"type": "mercadopago", "path": mp_csv},
    ]

    df = await run_pipeline(sources, usd_rate=1000.0)

    assert len(df) == 3
    # icbc has 2 rows, mp has 1 row

    # Sort order is ascending by date
    assert df.loc[0, "date"].strftime("%Y-%m-%d") == "2023-01-01"
    assert df.loc[1, "date"].strftime("%Y-%m-%d") == "2023-01-02"
    assert df.loc[2, "date"].strftime("%Y-%m-%d") == "2023-01-03"

    # Transfer logic should have flagged "PAGO VISA"
    assert bool(df.loc[1, "is_transfer"]) is True

    # FX
    assert df["amount_ars_equivalent"].notna().all()

    # Categorizer should have run
    assert df.loc[0, "category"] in ["Food", "Other"]

    # Schema check
    assert list(df.columns) == list(EXPECTED_SCHEMA.keys())
