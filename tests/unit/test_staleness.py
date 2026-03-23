"""Unit tests for the Staleness Guardrail."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone

from aegis.graph.staleness import check_staleness, staleness_node


@pytest.mark.asyncio
@patch("aegis.graph.staleness.get_connection")
async def test_check_staleness_fresh(mock_get_conn):
    # Mock fresh data (today)
    now = datetime.now(timezone.utc)
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.side_effect = [(now,), (now,)]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
    mock_get_conn.return_value.__aenter__.return_value = mock_conn
    
    warning = await check_staleness()
    assert warning is None

@pytest.mark.asyncio
@patch("aegis.graph.staleness.get_connection")
async def test_check_staleness_stale_transactions(mock_get_conn):
    # Mock stale transactions (40 days ago)
    stale_date = datetime.now(timezone.utc) - timedelta(days=40)
    fresh_date = datetime.now(timezone.utc)
    
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.side_effect = [(stale_date,), (fresh_date,)]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
    mock_get_conn.return_value.__aenter__.return_value = mock_conn
    
    warning = await check_staleness()
    assert "[STALE_DATA_WARNING]" in warning
    assert "Transactions are 40 days old" in warning

@pytest.mark.asyncio
@patch("aegis.graph.staleness.get_connection")
async def test_check_staleness_no_data(mock_get_conn):
    # Mock empty tables
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = (None,)
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
    mock_get_conn.return_value.__aenter__.return_value = mock_conn
    
    warning = await check_staleness()
    assert "[STALE_DATA_WARNING]" in warning
    assert "No transaction data imported yet" in warning
    assert "No exchange rates available" in warning

@pytest.mark.asyncio
@patch("aegis.graph.staleness.check_staleness", new_callable=AsyncMock)
async def test_staleness_node_prepends(mock_check):
    mock_check.return_value = "[WARNING]"
    
    state = {"final_answer": "My actual answer."}
    result = await staleness_node(state)
    
    assert result["final_answer"] == "[WARNING]\n\nMy actual answer."
