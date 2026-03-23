"""Unit tests for the SLM Categorizer."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd
from decimal import Decimal

from aegis.parsers.categorizer import SLMCategorizer, RuleBasedCategorizer, get_categorizer
from aegis.config import reset_config, get_config


@pytest.mark.asyncio
@patch("aegis.parsers.categorizer.httpx.AsyncClient.post")
async def test_slm_categorizer_success(mock_post):
    # Mock LLM response
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": '[{"category": "Food", "confidence": 0.95, "reasoning": "Grocery store"}]'
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp
    
    df = pd.DataFrame([{
        "description": "CARREFOUR",
        "amount_ars": 1000.0,
        "currency": "ARS"
    }])
    
    cat = SLMCategorizer()
    # Mock few-shot to avoid DB call
    with patch.object(cat, "_get_few_shot_examples", return_value=""):
        results = await cat.categorize_df(df)
        
    assert results.iloc[0]["category"] == "Food"
    assert results.iloc[0]["category_score"] == 0.95
    assert results.iloc[0]["is_flagged"] == False

@pytest.mark.asyncio
@patch("aegis.parsers.categorizer.httpx.AsyncClient.post")
async def test_slm_categorizer_low_confidence_flags(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "content": '[{"category": "Entertainment", "confidence": 0.5, "reasoning": "Unsure"}]'
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp
    
    df = pd.DataFrame([{
        "description": "UNKNOWN",
        "amount_ars": 100.0,
        "currency": "ARS"
    }])
    
    cat = SLMCategorizer()
    with patch.object(cat, "_get_few_shot_examples", return_value=""):
        results = await cat.categorize_df(df)
        
    assert results.iloc[0]["category"] == "Entertainment"
    assert results.iloc[0]["is_flagged"] == True

@pytest.mark.asyncio
@patch("aegis.parsers.categorizer.httpx.AsyncClient.post")
async def test_slm_categorizer_fallback_on_error(mock_post):
    # Mock server error
    mock_post.side_effect = Exception("Server down")
    
    df = pd.DataFrame([{
        "description": "CARREFOUR",
        "amount_ars": 1000.0,
        "currency": "ARS"
    }])
    
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
    with patch("aegis.config.Settings.model_validate") as mock_val:
        mock_settings = MagicMock()
        mock_settings.parser.categorizer_type = "slm"
        # Need to mock the whole singleton structure if we don't want to use real files
        pass
    
    # A simpler way to test the factory logic
    with patch("aegis.parsers.categorizer.get_config") as mock_get:
        mock_config = MagicMock()
        mock_config.parser.categorizer_type = "slm"
        mock_get.return_value = mock_config
        assert isinstance(get_categorizer(), SLMCategorizer)
        
        mock_config.parser.categorizer_type = "rule_based"
        assert isinstance(get_categorizer(), RuleBasedCategorizer)
