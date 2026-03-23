"""Unit tests for the SQL flow node."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from aegis.graph.sql_flow import (
    _extract_sql,
    _validate_syntax_and_whitelist,
    _check_currency_mixing,
    sql_flow_node,
)


def test_extract_sql():
    text = (
        "Here is your query:\n```sql\nSELECT * FROM v_net_worth;\n```\nHope this helps!"
    )
    sql = _extract_sql(text)
    assert sql == "SELECT * FROM v_net_worth;"

    # Test fallback without markdown
    text2 = "SELECT * FROM v_monthly_burn"
    assert _extract_sql(text2) == "SELECT * FROM v_monthly_burn"


def test_extract_sql_fails():
    with pytest.raises(ValueError):
        _extract_sql("This is not a SQL query")


def test_validate_syntax_and_whitelist_success():
    _validate_syntax_and_whitelist("SELECT total_ars FROM v_net_worth")
    _validate_syntax_and_whitelist(
        "SELECT * FROM v_monthly_burn JOIN v_category_spend ON ..."
    )


def test_validate_syntax_and_whitelist_fails_not_select():
    with pytest.raises(ValueError, match="Query must be a SELECT statement."):
        _validate_syntax_and_whitelist("DELETE FROM v_net_worth")


def test_validate_syntax_and_whitelist_fails_unauthorized_table():
    with pytest.raises(ValueError, match="unauthorized table/view: 'transactions'"):
        _validate_syntax_and_whitelist("SELECT * FROM transactions")


def test_check_currency_mixing():
    # Should warn
    assert _check_currency_mixing("SELECT SUM(amount) FROM v_monthly_burn") is not None
    # Should not warn
    assert (
        _check_currency_mixing(
            "SELECT SUM(amount) FROM v_monthly_burn GROUP BY currency"
        )
        is None
    )
    # Should not warn
    assert _check_currency_mixing("SELECT total_ars FROM v_net_worth") is None


@pytest.mark.asyncio
@patch("aegis.graph.sql_flow.select_relevant_views", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow._call_llm", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow._validate_schema", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow.get_connection")
async def test_sql_flow_node_success(
    mock_get_connection, mock_validate_schema, mock_call_llm, mock_select_views
):
    # Mock view selection
    mock_select_views.return_value = ["v_net_worth"]

    # Mock LLM to return valid SQL immediately
    mock_call_llm.return_value = "```sql\nSELECT total_ars FROM v_net_worth\n```"

    # Mock DB execution
    mock_conn = MagicMock()
    mock_cursor = AsyncMock()

    # Mock cursor.description to return a list of objects with a 'name' attribute
    column_mock = MagicMock()
    column_mock.name = "total_ars"
    mock_cursor.description = [column_mock]

    mock_cursor.fetchall.return_value = [[1500.0]]

    mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
    mock_get_connection.return_value.__aenter__.return_value = mock_conn

    state = {"query": "What is my ARS net worth?"}
    result = await sql_flow_node(state)

    assert "sql_result" in result
    assert len(result["sql_result"]) == 1
    assert result["sql_result"][0]["total_ars"] == 1500.0
    assert "Query executed successfully" in result["final_answer"]


@pytest.mark.asyncio
@patch("aegis.graph.sql_flow.select_relevant_views", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow._call_llm", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow._validate_schema", new_callable=AsyncMock)
async def test_sql_flow_node_retry_on_invalid_table(
    mock_validate_schema, mock_call_llm, mock_select_views
):
    mock_select_views.return_value = ["v_net_worth"]

    # First attempt: LLM uses unauthorized table
    # Second attempt: LLM corrects itself
    mock_call_llm.side_effect = [
        "```sql\nSELECT * FROM transactions\n```",
        "```sql\nSELECT * FROM v_net_worth\n```",
    ]

    # Mock that validate schema fails if it somehow gets there, but it shouldn't for the first query
    # However, we need to mock DB execution for the second successful attempt to avoid real DB connection
    with patch("aegis.graph.sql_flow.get_connection") as mock_get_connection:
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()
        column_mock = MagicMock()
        column_mock.name = "col1"
        mock_cursor.description = [column_mock]
        mock_cursor.fetchall.return_value = [["val1"]]
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        mock_get_connection.return_value.__aenter__.return_value = mock_conn

        state = {"query": "Test query"}
        result = await sql_flow_node(state)

        assert mock_call_llm.call_count == 2
        assert "Query executed successfully" in result["final_answer"]


@pytest.mark.asyncio
@patch("aegis.graph.sql_flow.select_relevant_views", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow._call_llm", new_callable=AsyncMock)
async def test_sql_flow_node_exhausts_retries(mock_call_llm, mock_select_views):
    mock_select_views.return_value = ["v_net_worth"]

    # LLM stubborn, always uses base table
    mock_call_llm.return_value = "```sql\nSELECT * FROM transactions\n```"

    state = {"query": "Test query"}
    result = await sql_flow_node(state)

    assert mock_call_llm.call_count == 3
    assert "could not generate a valid SQL query" in result["final_answer"]
