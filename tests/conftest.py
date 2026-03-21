# SPDX-License-Identifier: MIT
"""Shared fixtures for the Aegis Finance test suite."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Path constants ──────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_BANK_CSV = FIXTURES_DIR / "sample_bank.csv"

# ── Reusable test account UUID ──────────────────────────────────────────────

TEST_ACCOUNT_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture()
def sample_csv_path() -> Path:
    """Return the path to tests/fixtures/sample_bank.csv."""
    return SAMPLE_BANK_CSV


@pytest.fixture()
def test_account_id() -> UUID:
    """Return a deterministic UUID for test accounts."""
    return TEST_ACCOUNT_ID
