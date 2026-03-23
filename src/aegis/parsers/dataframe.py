from typing import Iterable
import pandas as pd
import numpy as np

from aegis.parsers.base import Transaction

EXPECTED_SCHEMA = {
    "date": "datetime64[ns]",
    "description": "object",
    "merchant_clean": "object",
    "amount_ars": "float64",
    "amount_usd": "float64",
    "amount_ars_equivalent": "float64",
    "currency": "object",
    "source": "object",
    "category": "object",
    "is_transfer": "bool",
    "is_flagged": "bool",
    "account_id": "object",
}


def to_dataframe(transactions: Iterable[Transaction], source: str) -> pd.DataFrame:
    """
    Converts a list of Transaction models into a unified pd.DataFrame.
    """
    records = []
    for t in transactions:
        amount_ars = float(t.amount) if t.currency == "ARS" else np.nan
        amount_usd = float(t.amount) if t.currency in {"USD", "USDT"} else np.nan

        description = t.merchant_raw if t.merchant_raw else t.description

        records.append(
            {
                "date": t.date,
                "description": description,
                "merchant_clean": t.merchant_clean,
                "amount_ars": amount_ars,
                "amount_usd": amount_usd,
                "amount_ars_equivalent": np.nan,
                "currency": t.currency,
                "source": source,
                "category": t.category,
                "is_transfer": False,
                "is_flagged": getattr(t, "is_flagged", False),
                "account_id": str(t.account_id),
            }
        )

    if not records:
        df = pd.DataFrame(columns=list(EXPECTED_SCHEMA.keys()))
    else:
        df = pd.DataFrame(records)

    # Cast to specific types
    df["date"] = pd.to_datetime(df["date"]).astype("datetime64[ns]")

    for col, dtype in EXPECTED_SCHEMA.items():
        if col not in df.columns:
            df[col] = pd.Series(dtype=dtype)
        elif df[col].dtype != dtype and col != "date":
            # Avoid casting date again, pandas handles object -> float64 differently sometimes
            if dtype == "float64":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(dtype)
            else:
                df[col] = df[col].astype(dtype)

    # Reorder columns to exactly match expected schema
    df = df[list(EXPECTED_SCHEMA.keys())]

    return df


def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validates column presence and dtypes against the unified schema.
    Raises ValueError listing missing columns or incorrect dtypes on failure.
    """
    missing_cols = [col for col in EXPECTED_SCHEMA if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing columns in DataFrame: {missing_cols}")

    wrong_dtypes = []
    for col, expected_dtype in EXPECTED_SCHEMA.items():
        actual_dtype = str(df[col].dtype)
        if expected_dtype == "datetime64[ns]" and "datetime64[ns" in actual_dtype:
            continue
        if actual_dtype != expected_dtype:
            wrong_dtypes.append(
                f"{col} (expected {expected_dtype}, got {actual_dtype})"
            )

    if wrong_dtypes:
        raise ValueError(f"Incorrect dtypes in DataFrame: {wrong_dtypes}")

    return df


def flag_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sets is_transfer = True for rows that represent internal account movements.
    This prevents double counting in P&L.
    """
    df = df.copy()
    if df.empty:
        return df

    # Rule 1: ICBC rows where description matches DEBIN or PREA
    icbc_mask = df["source"] == "icbc"
    debin_prea_mask = df["description"].str.contains(
        "DEBIN|PREA", na=False, case=False, regex=True
    )
    df.loc[icbc_mask & debin_prea_mask, "is_transfer"] = True

    # Rule 2: MercadoPago rows where description matches CUENTA ICBC
    mp_mask = df["source"] == "mercadopago"
    mp_icbc_mask = df["description"].str.contains("CUENTA ICBC", na=False, case=False)
    df.loc[mp_mask & mp_icbc_mask, "is_transfer"] = True

    # Rule 3: ICBC rows where description matches VISA or MASTERCARD
    card_mask = df["description"].str.contains(
        "VISA|MASTERCARD", na=False, case=False, regex=True
    )
    df.loc[icbc_mask & card_mask, "is_transfer"] = True

    return df


def apply_fx(df: pd.DataFrame, usd_rate: float = 1400.0) -> pd.DataFrame:
    """
    Populates amount_ars_equivalent using a point-in-time Dolar Tarjeta rate.
    Leaving amount_ars and amount_usd untouched.
    Note: usd_rate is a point-in-time rate, the caller is responsible for refreshing it.
    """
    df = df.copy()
    if df.empty:
        return df

    # Where amount_usd is not NaN, convert to ARS
    usd_mask = df["amount_usd"].notna()
    df.loc[usd_mask, "amount_ars_equivalent"] = (
        df.loc[usd_mask, "amount_usd"] * usd_rate
    )

    # Where amount_usd is NaN, use amount_ars
    ars_mask = df["amount_usd"].isna()
    df.loc[ars_mask, "amount_ars_equivalent"] = df.loc[ars_mask, "amount_ars"]

    return df
