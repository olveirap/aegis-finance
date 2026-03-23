# SPDX-License-Identifier: MIT
"""Rule-based transaction categorizer (baseline).

Loads keyword→category rules from a YAML file and assigns categories to
:class:`~aegis.parsers.base.Transaction` objects using substring and
word-boundary matching.  This module serves as the deterministic baseline;
Phase 2 will add an SLM-based categorizer that falls back to these rules
when confidence is low.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pandas as pd
import yaml

from aegis.parsers.base import Transaction

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "category_rules.yaml"
)

_SCORE_EXACT: float = 1.0
_SCORE_PARTIAL: float = 0.8
_FLAGGING_THRESHOLD: float = 0.85

# ── Internal data structures ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _CategoryRule:
    """Compiled matching rule for a single category."""

    name: str
    keywords: tuple[str, ...]
    partial: bool = True
    positive_only: bool = False
    # Pre-compiled word-boundary patterns for each keyword.
    _boundary_patterns: tuple[re.Pattern[str], ...] = field(
        default=(),
        repr=False,
    )


@dataclass(frozen=True, slots=True)
class _Match:
    """A candidate category match with its score."""

    category: str
    score: float


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_boundary_pattern(keyword: str) -> re.Pattern[str]:
    r"""Compile a regex that matches *keyword* at word boundaries.

    Uses ``\b`` on both sides so that ``"bar"`` matches the word *bar*
    but not the substring inside *embargo*.
    """
    return re.compile(r"\b" + re.escape(keyword) + r"\b")


def _load_rules(path: Path) -> list[_CategoryRule]:
    """Parse the YAML rules file into a list of :class:`_CategoryRule`."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict) or "categories" not in data:
        msg = f"Invalid rules file {path}: expected top-level 'categories' mapping"
        raise ValueError(msg)

    rules: list[_CategoryRule] = []
    for cat_name, cat_cfg in data["categories"].items():
        raw_keywords: list[str] = cat_cfg.get("keywords", [])
        # Normalise keywords to lowercase at load time.
        keywords = tuple(kw.lower().strip() for kw in raw_keywords if kw)
        partial = bool(cat_cfg.get("partial", True))
        positive_only = bool(cat_cfg.get("positive_only", False))

        patterns = tuple(_build_boundary_pattern(kw) for kw in keywords)

        rules.append(
            _CategoryRule(
                name=str(cat_name),
                keywords=keywords,
                partial=partial,
                positive_only=positive_only,
                _boundary_patterns=patterns,
            )
        )

    logger.info("Loaded %d category rules from %s", len(rules), path)
    return rules


def _normalise_text(merchant_raw: str | None, description: str | None) -> str:
    """Combine and lowercase merchant + description for matching."""
    parts: list[str] = []
    if merchant_raw:
        parts.append(merchant_raw)
    if description:
        parts.append(description)
    return " ".join(parts).lower()


# ── Public API ───────────────────────────────────────────────────────────────


class RuleBasedCategorizer:
    """Deterministic keyword-based transaction categorizer.

    Parameters
    ----------
    rules_path:
        Path to the ``category_rules.yaml`` file.  When *None*, the
        default path ``<project_root>/data/category_rules.yaml`` is used.
    """

    def __init__(self, rules_path: Path | None = None) -> None:
        resolved = rules_path or _DEFAULT_RULES_PATH
        self._rules = _load_rules(resolved)

    # ── Core matching ───────────────────────────────────────────────────

    def _find_matches(
        self,
        text: str,
        amount: Decimal,
    ) -> list[_Match]:
        """Return all category matches for *text*, scored and filtered."""
        matches: list[_Match] = []

        for rule in self._rules:
            # Skip positive_only rules when amount is not positive.
            if rule.positive_only and amount <= 0:
                continue

            best_score: float = 0.0

            for kw, boundary_re in zip(rule.keywords, rule._boundary_patterns):
                # Check substring presence first (cheap).
                if kw not in text:
                    continue

                # Found a substring hit — determine if it's an exact
                # (word-boundary) match or just a partial one.
                if boundary_re.search(text):
                    best_score = max(best_score, _SCORE_EXACT)
                    break  # Can't do better than 1.0.
                elif rule.partial:
                    best_score = max(best_score, _SCORE_PARTIAL)

            if best_score > 0.0:
                matches.append(_Match(category=rule.name, score=best_score))

        return matches

    def _resolve_matches(self, matches: list[_Match]) -> tuple[str, float, bool]:
        """Pick the winning category from a list of candidates.

        Returns
        -------
        tuple[str, float, bool]
            ``(category, score, is_flagged)``
        """
        if not matches:
            return "Other", 0.0, True

        # Sort descending by score.
        matches.sort(key=lambda m: m.score, reverse=True)
        top_score = matches[0].score

        # Collect all candidates that share the top score.
        top_matches = [m for m in matches if m.score == top_score]

        if len(top_matches) > 1:
            # Tie — flag for HITL review; pick the first alphabetically
            # for deterministic output.
            top_matches.sort(key=lambda m: m.category)
            winner = top_matches[0]
            logger.debug(
                "Tie between %s (score=%.2f); flagged for HITL",
                [m.category for m in top_matches],
                top_score,
            )
            return winner.category, winner.score, True

        winner = top_matches[0]
        flagged = winner.score < _FLAGGING_THRESHOLD
        return winner.category, winner.score, flagged

    # ── Public interface ────────────────────────────────────────────────

    def categorize(self, transaction: Transaction) -> Transaction:
        """Categorize a single transaction.

        Returns a **new** :class:`Transaction` with ``category``,
        ``category_score``, ``category_source``, and ``is_flagged`` set.
        The original object is not modified.
        """
        text = _normalise_text(transaction.merchant_raw, transaction.description)
        matches = self._find_matches(text, transaction.amount)
        category, score, flagged = self._resolve_matches(matches)

        return transaction.model_copy(
            update={
                "category": category,
                "category_score": score,
                "category_source": "auto",
                "is_flagged": flagged,
            },
        )

    def categorize_batch(
        self,
        transactions: list[Transaction],
    ) -> list[Transaction]:
        """Categorize a list of transactions.

        Returns a new list; the original transaction objects are not modified.
        """
        return [self.categorize(txn) for txn in transactions]

    def categorize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Categorize transactions in a DataFrame.

        Expects columns 'description', 'amount_ars', 'amount_usd', 'currency'.
        Returns a DataFrame with 'category', 'category_score', 'category_source', 'is_flagged'.
        """

        def _cat_row(row):
            text = (
                str(row["description"]).lower() if pd.notna(row["description"]) else ""
            )
            amount = (
                row["amount_usd"]
                if row["currency"] in {"USD", "USDT"}
                else row["amount_ars"]
            )
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
