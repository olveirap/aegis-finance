# SPDX-License-Identifier: MIT
"""Transaction categorizer using rule-based or SLM-based approaches.

Provides a strict keyword-based categorizer and an upgraded semantic classifier
using local Qwen 3.5.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from aegis.config import get_config
from aegis.db.connection import get_connection
from aegis.parsers.base import Transaction
from aegis.common.cloud_llm import CloudLLMClient

logger = logging.getLogger(__name__)


@dataclass
class CategoryMatch:
    """Represents a potential category match for a transaction."""

    category: str
    confidence: float
    source: str = "rule"
    is_flagged: bool = False


class RuleBasedCategorizer:
    """Strict keyword-based categorizer (Pass 1)."""

    def __init__(self, rules_path: Path | None = None) -> None:
        if rules_path is None:
            rules_path = (
                Path(__file__).resolve().parents[2]
                / ".."
                / "data"
                / "category_rules.yaml"
            )

        if not rules_path.exists():
            logger.warning(f"Category rules file not found: {rules_path}")
            self.rules = {}
        else:
            with open(rules_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.rules = data.get(
                    "categories", data
                )  # Support both flat and nested

    def categorize(self, txn: Transaction) -> Transaction:
        """Assign category to a single transaction."""
        text = str(txn.merchant_raw or "").lower()
        # Pass signed amount to respect positive_only rules
        amount = txn.amount

        matches = self._find_matches(text, amount)
        category, score, flagged = self._resolve_matches(matches)

        # Update transaction (mutate copy)
        new_txn = txn.model_copy()
        new_txn.category = category
        new_txn.category_score = score
        new_txn.category_source = "auto"
        new_txn.is_flagged = flagged or txn.is_flagged
        return new_txn

    def categorize_batch(self, transactions: list[Transaction]) -> list[Transaction]:
        """Categorize a list of transactions."""
        return [self.categorize(txn) for txn in transactions]

    def categorize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Categorize transactions in a DataFrame efficiently."""

        def _cat_row(row):
            text = (
                str(row["description"]).lower() if pd.notna(row["description"]) else ""
            )
            amount = (
                row["amount_usd"]
                if row["currency"] in {"USD", "USDT"}
                else row["amount_ars"]
            )
            # Use signed amount
            amount_dec = Decimal(str(amount)) if pd.notna(amount) else Decimal("0")

            matches = self._find_matches(text, amount_dec)
            category, score, flagged = self._resolve_matches(matches)
            return pd.Series([category, score, "auto", flagged])

        cat_results = df.apply(_cat_row, axis=1)
        cat_results.columns = [
            "category",
            "category_score",
            "category_source",
            "is_flagged",
        ]
        return cat_results

    def _find_matches(self, text: str, amount: Decimal) -> list[CategoryMatch]:
        matches = []
        for cat, config in self.rules.items():
            # Check positive_only flag
            if config.get("positive_only") and amount <= 0:
                continue

            # Keyword matching
            for kw in config.get("keywords", []):
                kw_low = kw.lower()
                if kw_low in text:
                    # Score: 1.0 for exact, 0.8 for partial
                    score = 1.0 if kw_low == text else 0.8
                    matches.append(CategoryMatch(cat, score))

            # Amount-based rules (e.g. high income)
            if amount > 500000 and cat == "Income" and "SUELDO" in text:
                matches.append(CategoryMatch(cat, 0.9))

        return matches

    def _resolve_matches(
        self, matches: list[CategoryMatch]
    ) -> tuple[str | None, float, bool]:
        if not matches:
            return "Other", 0.0, True  # Default to 'Other' and flag for review

        # Unique categories
        unique_cats = {m.category for m in matches}
        if len(unique_cats) > 1:
            # Conflict! Return top score but flag it
            top = max(matches, key=lambda x: x.confidence)
            return top.category, top.confidence, True

        top = max(matches, key=lambda x: x.confidence)
        # Flag if score is too low
        flagged = top.confidence < 0.85
        return top.category, top.confidence, flagged


class SLMCategorizer:
    """Semantic classifier using local Qwen 3.5 with rule-based fallback."""

    def __init__(self) -> None:
        self.rules = RuleBasedCategorizer()
        self.config = get_config()
        self.client = CloudLLMClient()

    async def categorize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Categorize transactions using SLM with fallback."""
        # If SLM is requested but server is down, fallback
        try:
            # 1. Fetch few-shot examples
            few_shot = await self._get_few_shot_examples()

            # 2. Prepare categories list
            allowed_cats = list(self.rules.rules.keys())

            # 3. Batch LLM call (processing in chunks of 10)
            results = []
            for i in range(0, len(df), 10):
                batch = df.iloc[i : i + 10]
                batch_res = await self._call_slm_batch(batch, allowed_cats, few_shot)
                results.extend(batch_res)

            # 4. Map results back to DataFrame
            cat_df = pd.DataFrame(results)
            return cat_df

        except Exception as e:
            logger.warning("SLM Categorization failed: %s. Falling back to rules.", e)
            return self.rules.categorize_df(df)

    async def _get_few_shot_examples(self) -> str:
        """Fetch historical user-corrected transactions for prompt."""
        try:
            async with get_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        SELECT merchant_raw, category
                        FROM transactions
                        WHERE category_source IN ('user', 'hitl')
                        AND category IS NOT NULL
                        LIMIT 10
                    """)
                    rows = await cur.fetchall()
                    if not rows:
                        return ""

                    ex_str = "\nExamples of previous categorizations:\n"
                    for row in rows:
                        ex_str += f"- '{row[0]}' -> {row[1]}\n"
                    return ex_str
        except Exception as e:
            logger.warning("Failed to fetch few-shot examples: %s", e)
            return ""

    async def _call_slm_batch(
        self, batch: pd.DataFrame, categories: list[str], few_shot: str
    ) -> list[dict[str, Any]]:
        """Call local LLM for a batch of transactions."""
        tx_list = []
        for _, row in batch.iterrows():
            tx_list.append(
                {
                    "description": row["description"],
                    "amount": row["amount_ars"]
                    if row["currency"] == "ARS"
                    else row["amount_usd"],
                    "currency": row["currency"],
                }
            )

        system_prompt = f"""You are a financial personal assistant. Your task is to categorize bank transactions.
Allowed Categories: {", ".join(categories)}
{few_shot}
Output ONLY a JSON list of objects, one for each input transaction in order.
Each object must have:
- "category": the chosen category string
- "confidence": a score between 0.0 and 1.0
- "reasoning": a short string explaining why
"""

        user_prompt = f"Categorize these transactions:\n{json.dumps(tx_list)}"

        try:
            content = await self.client.generate(
                system_prompt,
                user_prompt,
                temperature=0.0,
                response_format={"type": "json_object"},
            )

            # Robust parsing
            # Sometimes models wrap in ```json
            clean_content = content.strip()
            if clean_content.startswith("```"):
                clean_content = re.sub(r"```json\s*|\s*```", "", clean_content)

            # Check if it's a list directly or an object with a 'transactions' key
            parsed = json.loads(clean_content)
            if isinstance(parsed, dict) and "transactions" in parsed:
                parsed = parsed["transactions"]

            final_results = []
            for i, res in enumerate(parsed):
                cat = res.get("category")
                conf = float(res.get("confidence", 0.0))

                # Validate category
                if cat not in categories:
                    # Fallback to rules for this specific row if LLM hallucinated category
                    row = batch.iloc[i]
                    rule_res = self.rules.categorize_df(pd.DataFrame([row])).iloc[0]
                    final_results.append(rule_res.to_dict())
                else:
                    final_results.append(
                        {
                            "category": cat,
                            "category_score": conf,
                            "category_source": "auto",
                            "is_flagged": conf < 0.75,
                        }
                    )
            return final_results
        except Exception as e:
            logger.error("Failed to process SLM batch: %s", e)
            raise ValueError("SLM processing failed") from e


def get_categorizer() -> RuleBasedCategorizer | SLMCategorizer:
    """Factory function to get the configured categorizer."""
    config = get_config()
    if config.parser.categorizer_type == "slm":
        return SLMCategorizer()
    return RuleBasedCategorizer()
