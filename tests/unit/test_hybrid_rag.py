"""Unit tests for the Hybrid RAG Pipeline."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from aegis.graph.hybrid_flow import hybrid_flow_node
from aegis.graph.rag_flow import rag_flow_node
from aegis.common.cloud_llm import CloudLLMClient


@pytest.mark.asyncio
@patch("aegis.graph.hybrid_flow.sql_flow_node", new_callable=AsyncMock)
@patch("aegis.graph.hybrid_flow.privacy_node", new_callable=AsyncMock)
@patch("aegis.graph.hybrid_flow.Retriever.retrieve", new_callable=AsyncMock)
@patch("aegis.graph.hybrid_flow.CloudLLMClient.generate", new_callable=AsyncMock)
async def test_hybrid_flow_node(mock_generate, mock_retrieve, mock_privacy, mock_sql):
    # Mock SQL
    mock_sql.return_value = {"sql_result": [{"total_ars": 1000}]}

    # Mock Privacy
    mock_privacy.return_value = {
        "privacy_output": {
            "sanitized_query": "Analysis for [PERSON_1]",
            "sanitized_context": "[{'total_ars': 1000}]",
            "redaction_map": {"[PERSON_1]": "Juan"},
            "risk_score": 0.01,
        }
    }

    # Mock RAG
    mock_retrieve.return_value = [
        {
            "content": "Knowledge about saving.",
            "source_title": "Blog",
            "source": "http://blog.com",
        }
    ]

    # Mock Cloud LLM
    mock_generate.return_value = "Hello [PERSON_1], you have 1000 ARS."

    state = {"query": "Analysis for Juan"}
    result = await hybrid_flow_node(state)

    assert result["final_answer"] == "Hello Juan, you have 1000 ARS."
    assert "privacy_output" in result
    assert len(result["rag_chunks"]) == 1


@pytest.mark.asyncio
@patch("aegis.graph.rag_flow.privacy_node", new_callable=AsyncMock)
@patch("aegis.graph.rag_flow.Retriever.retrieve", new_callable=AsyncMock)
@patch("aegis.graph.rag_flow.CloudLLMClient.generate", new_callable=AsyncMock)
async def test_rag_flow_node(mock_generate, mock_retrieve, mock_privacy):
    # Mock Privacy
    mock_privacy.return_value = {
        "privacy_output": {
            "sanitized_query": "Tell me about [ENTITY_1]",
            "redaction_map": {"[ENTITY_1]": "Fixed Term"},
            "risk_score": 0.01,
        }
    }

    # Mock RAG
    mock_retrieve.return_value = [
        {
            "content": "A fixed term is...",
            "source_title": "BCRA",
            "source": "http://bcra.gob.ar",
        }
    ]

    # Mock synthesis
    mock_generate.return_value = "A fixed term is a type of investment."

    state = {"query": "Tell me about Fixed Term"}
    result = await rag_flow_node(state)

    assert result["final_answer"] == "A fixed term is a type of investment."
    assert len(result["rag_chunks"]) == 1


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_cloud_llm_fallback(mock_post):
    # Mock local llama.cpp response
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Local response"}}]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    client = CloudLLMClient()
    # Force fallback by ensuring no cloud client is initialized (default in tests usually)
    client.client = None

    response = await client.generate("system", "user")
    assert response == "Local response"
    assert mock_post.called
