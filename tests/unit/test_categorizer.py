# SPDX-License-Identifier: MIT
"""Unit tests for the RuleBasedCategorizer (Task 1.6).

The categorizer module may not be implemented yet.  These tests define the
expected behaviour based on the Phase 1 spec so they serve as a contract
for development.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

# This import will fail until the categorizer module is created.
# Mark the entire module so the suite doesn't hard-crash.
try:
    from aegis.parsers.categorizer import RuleBasedCategorizer

    _HAS_CATEGORIZER = True
except ImportError:
    _HAS_CATEGORIZER = False

from aegis.parsers.base import Transaction

pytestmark = pytest.mark.skipif(
    not _HAS_CATEGORIZER,
    reason="aegis.parsers.categorizer not implemented yet",
)

# ── Constants ────────────────────────────────────────────────────────────────

ACCT = UUID("12345678-1234-5678-1234-567812345678")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _txn(
    merchant: str | None = "UNKNOWN MERCHANT",
    amount: Decimal = Decimal("-1000.00"),
    **kw,
) -> Transaction:
    """Create a minimal Transaction for categorizer tests."""
    defaults = {
        "date": date(2026, 1, 15),
        "amount": amount,
        "currency": "ARS",
        "merchant_raw": merchant,
        "account_id": ACCT,
    }
    defaults.update(kw)
    return Transaction(**defaults)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def categorizer() -> RuleBasedCategorizer:
    """Return a fresh RuleBasedCategorizer with default rules."""
    return RuleBasedCategorizer()


# ── Exact / partial match tests ──────────────────────────────────────────────


class TestCategoryMatching:
    """Rule-based category assignment."""

    def test_exact_match_food(self, categorizer: RuleBasedCategorizer) -> None:
        """CARREFOUR should be categorized as Food."""
        txn = _txn(merchant="CARREFOUR")
        result = categorizer.categorize(txn)
        assert result.category == "Food"
        assert result.category_score is not None
        assert result.category_score >= 0.8

    def test_partial_match_transport(self, categorizer: RuleBasedCategorizer) -> None:
        """'SUBE CARGA' should match Transportation."""
        txn = _txn(merchant="SUBE CARGA")
        result = categorizer.categorize(txn)
        assert result.category == "Transportation"

    def test_income_positive_amount(self, categorizer: RuleBasedCategorizer) -> None:
        """Positive amount with 'SUELDO' keyword should be Income."""
        txn = _txn(merchant="SUELDO EMPRESA TECH SA", amount=Decimal("950000.00"))
        result = categorizer.categorize(txn)
        assert result.category == "Income"

    def test_income_negative_amount_not_matched(
        self, categorizer: RuleBasedCategorizer
    ) -> None:
        """Negative amount with 'SUELDO' should NOT be categorized as Income
        if the categorizer respects a positive_only flag for income rules."""
        txn = _txn(merchant="SUELDO DEVOLUCION", amount=Decimal("-50000.00"))
        result = categorizer.categorize(txn)
        # Should not be Income — either Other or some other category
        assert result.category != "Income"


# ── Flagging tests ───────────────────────────────────────────────────────────


class TestFlagging:
    """Transactions that require human review should be flagged."""

    def test_no_match_flagged(self, categorizer: RuleBasedCategorizer) -> None:
        """Unknown merchant should → Other, is_flagged=True, score=0.0."""
        txn = _txn(merchant="XYZZY TOTALLY UNKNOWN 99")
        result = categorizer.categorize(txn)
        assert result.category == "Other"
        assert result.is_flagged is True
        assert result.category_score == pytest.approx(0.0)

    def test_multi_category_conflict_flagged(
        self, categorizer: RuleBasedCategorizer
    ) -> None:
        """A merchant matching multiple categories should be flagged."""
        # A merchant name designed to match both Food and Health rules
        txn = _txn(merchant="FARMACIA SUPERMERCADO")
        result = categorizer.categorize(txn)
        assert result.is_flagged is True

    def test_low_score_flagged(self, categorizer: RuleBasedCategorizer) -> None:
        """If category_score < 0.85 the transaction should be flagged."""
        # Use a vague merchant that might get a partial/low-confidence match
        txn = _txn(merchant="MP - PAGO")
        result = categorizer.categorize(txn)
        if result.category_score is not None and result.category_score < 0.85:
            assert result.is_flagged is True


# ── Batch & edge case tests ──────────────────────────────────────────────────


class TestBatchAndEdgeCases:
    """Batch processing and edge cases."""

    def test_categorize_batch(self, categorizer: RuleBasedCategorizer) -> None:
        """categorize_batch should process a list and return results."""
        txns = [
            _txn(merchant="CARREFOUR"),
            _txn(merchant="SUBE CARGA"),
            _txn(merchant="UNKNOWN VENDOR"),
        ]
        results = categorizer.categorize_batch(txns)
        assert len(results) == 3
        # Each result must have a category assigned
        for r in results:
            assert r.category is not None

    def test_categorize_df(self, categorizer: RuleBasedCategorizer) -> None:
        """categorize_df should process a DataFrame and return results."""
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "description": "CARREFOUR",
                    "amount_ars": -1000.0,
                    "amount_usd": None,
                    "currency": "ARS",
                },
                {
                    "description": "SUBE CARGA",
                    "amount_ars": -500.0,
                    "amount_usd": None,
                    "currency": "ARS",
                },
                {
                    "description": "SUELDO",
                    "amount_ars": 1000000.0,
                    "amount_usd": None,
                    "currency": "ARS",
                },
            ]
        )
        results = categorizer.categorize_df(df)
        assert len(results) == 3
        assert results.iloc[0]["category"] == "Food"
        assert results.iloc[1]["category"] == "Transportation"
        assert results.iloc[2]["category"] == "Income"

    def test_empty_merchant(self, categorizer: RuleBasedCategorizer) -> None:
        """None or empty merchant_raw must be handled gracefully (no crash)."""
        txn_none = _txn(merchant=None)
        result_none = categorizer.categorize(txn_none)
        assert result_none.category is not None  # should default to something

        txn_empty = _txn(merchant="")
        result_empty = categorizer.categorize(txn_empty)
        assert result_empty.category is not None

    def test_does_not_mutate_original(self, categorizer: RuleBasedCategorizer) -> None:
        """The original Transaction object must not be modified in place."""
        txn = _txn(merchant="CARREFOUR")
        original = copy.deepcopy(txn)
        _result = categorizer.categorize(txn)
        # The original should still have no category set
        assert txn.category == original.category
        assert txn.is_flagged == original.is_flagged
        assert txn.category_score == original.category_score
