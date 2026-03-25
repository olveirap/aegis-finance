"""Unit tests for the SLM Categorizer."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd

from aegis.parsers.categorizer import (
    SLMCategorizer,
    RuleBasedCategorizer,
    get_categorizer,
)
from aegis.config import reset_config


@pytest.mark.asyncio
@patch("aegis.common.cloud_llm.CloudLLMClient.generate", new_callable=AsyncMock)
async def test_slm_categorizer_success(mock_generate):
    # Mock LLM response
    mock_generate.return_value = (
        '[{"category": "Food", "confidence": 0.95, "reasoning": "Grocery store"}]'
    )

    df = pd.DataFrame(
        [{"description": "CARREFOUR", "amount_ars": 1000.0, "currency": "ARS"}]
    )

    cat = SLMCategorizer()
    # Mock few-shot to avoid DB call
    with patch.object(cat, "_get_few_shot_examples", return_value=""):
        results = await cat.categorize_df(df)

    assert results.iloc[0]["category"] == "Food"
    assert results.iloc[0]["category_score"] == 0.95
    assert not results.iloc[0]["is_flagged"]


@pytest.mark.asyncio
@patch("aegis.common.cloud_llm.CloudLLMClient.generate", new_callable=AsyncMock)
async def test_slm_categorizer_low_confidence_flags(mock_generate):
    mock_generate.return_value = (
        '[{"category": "Entertainment", "confidence": 0.5, "reasoning": "Unsure"}]'
    )

    df = pd.DataFrame(
        [{"description": "UNKNOWN", "amount_ars": 100.0, "currency": "ARS"}]
    )

    cat = SLMCategorizer()
    with patch.object(cat, "_get_few_shot_examples", return_value=""):
        results = await cat.categorize_df(df)

    assert results.iloc[0]["category"] == "Entertainment"
    assert results.iloc[0]["is_flagged"]


@pytest.mark.asyncio
@patch("aegis.common.cloud_llm.CloudLLMClient.generate", new_callable=AsyncMock)
async def test_slm_categorizer_fallback_on_error(mock_generate):
    # Mock server error
    mock_generate.side_effect = Exception("Server down")

    df = pd.DataFrame(
        [{"description": "CARREFOUR", "amount_ars": 1000.0, "currency": "ARS"}]
    )

    cat = SLMCategorizer()
    with patch.object(cat, "_get_few_shot_examples", return_value=""):
        results = await cat.categorize_df(df)

    # Should fallback to RuleBasedCategorizer which knows CARREFOUR -> Food
    assert results.iloc[0]["category"] == "Food"
    assert results.iloc[0]["category_source"] == "auto"


def test_get_categorizer_config():
    reset_config()
    # Default is rule_based
    assert isinstance(get_categorizer(), RuleBasedCategorizer)

    # Mock config to SLM
    with patch("aegis.parsers.categorizer.get_config") as mock_get:
        mock_config = MagicMock()
        mock_config.parser.categorizer_type = "slm"
        mock_get.return_value = mock_config
        assert isinstance(get_categorizer(), SLMCategorizer)

        mock_config.parser.categorizer_type = "rule_based"
        assert isinstance(get_categorizer(), RuleBasedCategorizer)
