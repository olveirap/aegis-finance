"""Unit tests for the Privacy Middleware."""

import pytest
from unittest.mock import patch, AsyncMock

from aegis.privacy.redaction_map import RedactionMap
from aegis.privacy.regex_scrubber import RegexScrubber
from aegis.privacy.semantic_scrubber import SemanticScrubber
from aegis.privacy.risk_scorer import RiskScorer
from aegis.graph.privacy import privacy_node


def test_redaction_map_bidirectional():
    rmap = RedactionMap()
    token = rmap.get_token("Juan Perez", "PERSON")
    assert token == "[PERSON_1]"

    # Re-request same value
    assert rmap.get_token("Juan Perez", "PERSON") == "[PERSON_1]"

    # Request different value
    token2 = rmap.get_token("Maria Garcia", "PERSON")
    assert token2 == "[PERSON_2]"

    # Reconstruction
    text = "Hello [PERSON_1] and [PERSON_2]."
    restored = rmap.reconstruct(text)
    assert restored == "Hello Juan Perez and Maria Garcia."


def test_regex_scrubber_patterns():
    rmap = RedactionMap()
    scrubber = RegexScrubber()

    # CUIT
    text = "Mi CUIT es 20-12345678-9."
    scrubbed = scrubber.scrub(text, rmap)
    assert "[CUIT_1]" in scrubbed
    assert "20-12345678-9" not in scrubbed

    # Email
    text = "Contact me at test@example.com."
    scrubbed = scrubber.scrub(text, rmap)
    assert "[EMAIL_1]" in scrubbed
    assert "test@example.com" not in scrubbed


def test_regex_scrubber_bucketing():
    rmap = RedactionMap()
    scrubber = RegexScrubber()

    # Bucketing ARS ($15.200 -> [ARS_10k_50k])
    # Note: buckets are [0, 50_000, 500_000, ...]
    # $15.200 is between 0 and 50.000
    text = "Gasté $15.200 en el super."
    scrubbed = scrubber.scrub(text, rmap)
    assert "[ARS_0_50k]" in scrubbed

    # Bucketing USD
    text = "Tengo USD 1500."
    scrubbed = scrubber.scrub(text, rmap)
    assert "[USD_1k_10k]" in scrubbed


@pytest.mark.asyncio
@patch(
    "aegis.privacy.semantic_scrubber.SemanticScrubber._call_llm", new_callable=AsyncMock
)
async def test_semantic_scrubber(mock_call):
    rmap = RedactionMap()
    scrubber = SemanticScrubber()

    # Mock LLM to find an address
    mock_call.return_value = '["Av. Siempreviva 742"]'

    text = "I live in Av. Siempreviva 742."
    scrubbed = await scrubber.scrub(text, rmap)

    assert "[ENTITY_1]" in scrubbed
    assert "Av. Siempreviva 742" not in scrubbed
    assert rmap.reconstruct(scrubbed) == text


def test_risk_scorer_basic():
    # This might use the real Presidio if available, or mock if we want isolation
    scorer = RiskScorer()

    # High risk text (unsrubbed)
    high_risk = "My name is John Doe and my phone is 555-1234. I live in New York."
    # Low risk text
    low_risk = "How do I save money?"

    # We check relative risk because absolute values depend on Presidio config
    score_high = scorer.calculate_risk(high_risk)
    score_low = scorer.calculate_risk(low_risk)

    assert score_high >= score_low


@pytest.mark.asyncio
@patch("aegis.graph.privacy.SemanticScrubber.scrub", new_callable=AsyncMock)
@patch("aegis.graph.privacy.RiskScorer.calculate_risk")
async def test_privacy_node_blocks_high_risk(mock_calculate, mock_semantic_scrub):
    mock_semantic_scrub.side_effect = lambda x, m: x  # Return text as is
    mock_calculate.return_value = 0.9  # Very high risk

    state = {"query": "Tell me my secrets."}
    result = await privacy_node(state)

    assert "final_answer" in result
    assert "risk threshold" in result["final_answer"]
    assert result["privacy_output"]["risk_score"] == 0.9
