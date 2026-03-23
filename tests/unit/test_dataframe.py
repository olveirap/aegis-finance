import pytest
import pandas as pd
import numpy as np
from datetime import date
from decimal import Decimal
from uuid import uuid4

from aegis.parsers.base import Transaction
from aegis.parsers.dataframe import (
    to_dataframe,
    enforce_schema,
    flag_transfers,
    apply_fx,
)


@pytest.fixture
def sample_transactions():
    acc_id = uuid4()
    return [
        Transaction(
            date=date(2023, 1, 1),
            amount=Decimal("-100.50"),
            currency="ARS",
            merchant_raw="MERCADO LIBRE",
            description="Compra",
            account_id=acc_id,
        ),
        Transaction(
            date=date(2023, 1, 2),
            amount=Decimal("-50.00"),
            currency="USD",
            merchant_raw="AMAZON",
            account_id=acc_id,
        ),
        Transaction(
            date=date(2023, 1, 3),
            amount=Decimal("200.00"),
            currency="USDT",
            description="Crypto deposit",
            account_id=acc_id,
        ),
    ]


def test_to_dataframe(sample_transactions):
    df = to_dataframe(sample_transactions, source="test_source")

    assert len(df) == 3
    expected_columns = [
        "date",
        "description",
        "merchant_clean",
        "amount_ars",
        "amount_usd",
        "amount_ars_equivalent",
        "currency",
        "source",
        "category",
        "is_transfer",
        "is_flagged",
        "account_id",
    ]
    assert list(df.columns) == expected_columns
    assert df["source"].unique() == ["test_source"]
    assert df["is_transfer"].unique() == [False]
    assert df["amount_ars_equivalent"].isna().all()
    assert df["date"].dtype == "datetime64[ns]"

    # ARS transaction
    assert df.loc[0, "amount_ars"] == -100.50
    assert pd.isna(df.loc[0, "amount_usd"])
    assert df.loc[0, "description"] == "MERCADO LIBRE"  # merchant_raw fallback

    # USD transaction
    assert pd.isna(df.loc[1, "amount_ars"])
    assert df.loc[1, "amount_usd"] == -50.00
    assert df.loc[1, "description"] == "AMAZON"

    # USDT transaction
    assert pd.isna(df.loc[2, "amount_ars"])
    assert df.loc[2, "amount_usd"] == 200.00
    assert df.loc[2, "description"] == "Crypto deposit"


def test_to_dataframe_empty():
    df = to_dataframe([], source="empty")
    assert len(df) == 0
    assert "amount_ars" in df.columns
    assert "date" in df.columns
    assert df["date"].dtype == "datetime64[ns]"


def test_enforce_schema_valid(sample_transactions):
    df = to_dataframe(sample_transactions, source="test")
    # Should not raise
    validated = enforce_schema(df)
    assert validated is df


def test_enforce_schema_invalid():
    df = pd.DataFrame({"date": ["2023-01-01"], "amount_ars": [100]})
    with pytest.raises(ValueError, match="Missing columns"):
        enforce_schema(df)

    df_wrong_type = pd.DataFrame(
        {
            "date": ["2023-01-01"],
            "description": ["A"],
            "merchant_clean": ["A"],
            "amount_ars": ["100"],
            "amount_usd": [10],
            "amount_ars_equivalent": [10],
            "currency": ["ARS"],
            "source": ["test"],
            "category": ["Food"],
            "is_transfer": [False],
            "is_flagged": [False],
            "account_id": ["123"],
        }
    )
    with pytest.raises(ValueError, match="Incorrect dtype"):
        enforce_schema(df_wrong_type)


def test_flag_transfers():
    df = pd.DataFrame(
        {
            "description": [
                "DEBIN A JUAN",
                "PREA COMPRA",
                "SUPERMERCADO",
                "CUENTA ICBC",
                "PAGO VISA",
                "MASTERCARD 1234",
                "Netflix",
            ],
            "source": ["icbc", "icbc", "icbc", "mercadopago", "icbc", "icbc", "visa"],
        }
    )
    df["is_transfer"] = False

    result = flag_transfers(df)

    expected = [True, True, False, True, True, True, False]
    assert result["is_transfer"].tolist() == expected
    assert not df["is_transfer"].any()  # non-destructive


def test_apply_fx():
    df = pd.DataFrame(
        {
            "amount_ars": [-100.0, np.nan, np.nan],
            "amount_usd": [np.nan, -50.0, 200.0],
            "amount_ars_equivalent": [np.nan, np.nan, np.nan],
        }
    )

    result = apply_fx(df, usd_rate=1400.0)

    assert result.loc[0, "amount_ars_equivalent"] == -100.0
    assert result.loc[1, "amount_ars_equivalent"] == -50.0 * 1400.0
    assert result.loc[2, "amount_ars_equivalent"] == 200.0 * 1400.0

    assert df["amount_ars_equivalent"].isna().all()  # non-destructive
