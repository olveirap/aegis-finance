"""Unit tests for the Anonymized Research Tools."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from aegis.tools.search import search_duckduckgo
from aegis.tools.browser import is_whitelisted, browse_url
from aegis.graph.research_flow import research_flow_node


def test_is_whitelisted():
    assert is_whitelisted("https://www.bcra.gob.ar/default.asp") is True
    assert is_whitelisted("http://ambito.com/noticias") is True
    assert is_whitelisted("https://sub.afip.gob.ar/index.html") is True
    assert is_whitelisted("https://google.com/search") is False
    assert is_whitelisted("https://evil.bcra.gob.ar.attacker.com") is False


@pytest.mark.asyncio
@patch("aegis.tools.search.DDGS")
async def test_search_duckduckgo(mock_ddgs):
    # Mock DDGS context manager and text search
    mock_instance = MagicMock()
    mock_instance.text.return_value = [
        {"title": "Test Title", "href": "http://test.com", "body": "Test Body"}
    ]
    mock_ddgs.return_value.__enter__.return_value = mock_instance

    results = await search_duckduckgo("anonymized query")
    assert len(results) == 1
    assert results[0]["title"] == "Test Title"


@pytest.mark.asyncio
@patch("trafilatura.fetch_url")
@patch("trafilatura.extract")
async def test_browse_url_whitelisted(mock_extract, mock_fetch):
    mock_fetch.return_value = "<html><body>Content</body></html>"
    mock_extract.return_value = "Extracted Content"

    url = "https://www.bcra.gob.ar/data"
    content = await browse_url(url)

    assert content == "Extracted Content"
    mock_fetch.assert_called_once_with(url)


@pytest.mark.asyncio
async def test_browse_url_not_whitelisted():
    url = "https://facebook.com/someone"
    content = await browse_url(url)
    assert content is None


@pytest.mark.asyncio
@patch("aegis.graph.research_flow.privacy_node", new_callable=AsyncMock)
@patch("aegis.graph.research_flow.search_duckduckgo", new_callable=AsyncMock)
@patch("aegis.graph.research_flow.browse_url", new_callable=AsyncMock)
@patch("aegis.graph.research_flow._synthesize_research", new_callable=AsyncMock)
async def test_research_flow_node(mock_synth, mock_browse, mock_search, mock_privacy):
    # Mock Privacy Pass
    mock_privacy.return_value = {
        "privacy_output": {
            "sanitized_query": "What is [ENTITY_1]?",
            "redaction_map": {"[ENTITY_1]": "BCRA"},
        }
    }

    # Mock Search
    mock_search.return_value = [
        {"title": "BCRA Info", "href": "https://bcra.gob.ar/info", "body": "Snippet"}
    ]

    # Mock Browser
    mock_browse.return_value = "Long page content about BCRA."

    # Mock Synthesis
    mock_synth.return_value = "The BCRA is the central bank."

    state = {"query": "What is BCRA?"}
    result = await research_flow_node(state)

    assert result["final_answer"] == "The BCRA is the central bank."
    assert "privacy_output" in result
    assert result["tool_results"] == mock_search.return_value
