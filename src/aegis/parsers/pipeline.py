import logging
from pathlib import Path
import pandas as pd
from uuid import UUID

from aegis.parsers.dataframe import (
    to_dataframe,
    flag_transfers,
    apply_fx,
    enforce_schema,
    EXPECTED_SCHEMA,
)
from aegis.parsers.icbc import ICBCParser
from aegis.parsers.mercadopago import MercadoPagoParser
from aegis.parsers.credit_card import CreditCardParser
from aegis.parsers.categorizer import RuleBasedCategorizer

logger = logging.getLogger(__name__)

# Default sentinel UUID if none provided
SENTINEL_UUID = UUID("00000000-0000-0000-0000-000000000000")


async def run_pipeline(sources: list[dict], usd_rate: float = 1400.0) -> pd.DataFrame:
    """
    Wires together all parsers and enrichment steps, returning a unified DataFrame.

    Args:
        sources: List of dicts with keys 'type', 'path', and optionally 'account_id'.
        usd_rate: Point-in-time USD to ARS exchange rate.
    """
    if not sources:
        df = pd.DataFrame(columns=list(EXPECTED_SCHEMA.keys()))
        for col, dtype in EXPECTED_SCHEMA.items():
            if dtype == "datetime64[ns]":
                df[col] = pd.Series(dtype=dtype)
            else:
                df[col] = pd.Series(dtype=dtype)
        return df

    dfs = []

    for source in sources:
        src_type = source["type"]
        path = Path(source["path"])
        account_id = source.get("account_id")

        if isinstance(account_id, str):
            account_id = UUID(account_id)
        elif account_id is None:
            account_id = SENTINEL_UUID

        if src_type == "icbc":
            parser = ICBCParser(account_id=account_id)
        elif src_type == "mercadopago":
            parser = MercadoPagoParser(account_id=account_id)
        elif src_type in ("visa", "mastercard"):
            parser = CreditCardParser(account_id=account_id, card_brand=src_type)
        else:
            raise ValueError(f"Unknown source type: {src_type}")

        transactions = parser.parse(path)
        df = to_dataframe(transactions, source=src_type)
        dfs.append(df)

    combined_df = (
        pd.concat(dfs, ignore_index=True)
        if dfs
        else pd.DataFrame(columns=list(EXPECTED_SCHEMA.keys()))
    )

    if combined_df.empty:
        return enforce_schema(combined_df)

    combined_df = flag_transfers(combined_df)
    combined_df = apply_fx(combined_df, usd_rate=usd_rate)

    # Run RuleBasedCategorizer
    categorizer = RuleBasedCategorizer()
    cat_results = categorizer.categorize_df(combined_df)

    combined_df["category"] = cat_results["category"].values
    combined_df["is_flagged"] = cat_results["is_flagged"].values

    combined_df = combined_df.sort_values(by="date", ascending=True).reset_index(
        drop=True
    )

    # Ensure types are perfect before returning to pass enforce_schema
    for col, dtype in EXPECTED_SCHEMA.items():
        if combined_df[col].dtype != dtype and col != "date":
            if dtype == "float64":
                combined_df[col] = pd.to_numeric(
                    combined_df[col], errors="coerce"
                ).astype(dtype)
            else:
                combined_df[col] = combined_df[col].astype(dtype)

    return enforce_schema(combined_df)
