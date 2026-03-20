# SPDX-License-Identifier: MIT
"""Unit tests for the LangGraph router node.

Tests query classification into 5 categories with mocked llama.cpp responses.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from aegis.graph.router import (
    QUERY_TYPE_CONFIG,
    QueryType,
    RouterOutput,
    _heuristic_router,
    _parse_router_response,
    router_node,
)


# =============================================================================
# Test Data
# =============================================================================

TEST_QUERIES = [
    # (query, expected_type, expected_route, requires_cloud, requires_tools)
    # PERSONAL_FINANCIAL (3 queries)
    ("¿Cuál es mi patrimonio neto actual?", QueryType.PERSONAL_FINANCIAL, "sql", False, False),
    ("¿Cuánto gasté en supermercado el mes pasado?", QueryType.PERSONAL_FINANCIAL, "sql", False, False),
    ("Muestra mis ingresos de los últimos 3 meses", QueryType.PERSONAL_FINANCIAL, "sql", False, False),

    # MARKET_KNOWLEDGE (3 queries)
    ("¿Qué es un CEDEAR?", QueryType.MARKET_KNOWLEDGE, "rag", False, False),
    ("Explicame cómo funciona el dólar MEP", QueryType.MARKET_KNOWLEDGE, "rag", False, False),
    ("¿Qué impuestos pago por vender acciones?", QueryType.MARKET_KNOWLEDGE, "rag", False, False),

    # HYBRID (2 queries)
    ("¿Debería comprar más acciones dado mi patrimonio actual?", QueryType.HYBRID, "hybrid", True, False),
    ("Con mi nivel de gastos, ¿puedo permitirme invertir $1000 USD?", QueryType.HYBRID, "hybrid", True, False),

    # GENERAL_FINANCE (2 queries)
    ("¿Cuál es la regla del 72 en inversiones?", QueryType.GENERAL_FINANCE, "general", False, False),
    ("Explicame qué es el interés compuesto", QueryType.GENERAL_FINANCE, "general", False, False),

    # RESEARCH (2 queries)
    ("¿Cuál es la tasa de inflación en Argentina hoy?", QueryType.RESEARCH, "research", False, True),
    ("Busca las últimas noticias sobre el BCRA", QueryType.RESEARCH, "research", False, True),
]


# =============================================================================
# RouterOutput Tests
# =============================================================================

class TestRouterOutput:
    """Tests for the RouterOutput class."""

    def test_router_output_creation(self) -> None:
        """Test RouterOutput creation with valid data."""
        data = {
            "route": "sql",
            "query_type": "PERSONAL_FINANCIAL",
            "requires_cloud": False,
            "requires_tools": False,
            "reasoning": "Test reasoning",
        }
        output = RouterOutput(data)

        assert output.route == "sql"
        assert output.query_type == "PERSONAL_FINANCIAL"
        assert output.requires_cloud is False
        assert output.requires_tools is False
        assert output.reasoning == "Test reasoning"

    def test_router_output_missing_fields(self) -> None:
        """Test RouterOutput raises ValueError for missing required fields."""
        data = {"route": "sql"}  # Missing required fields

        with pytest.raises(ValueError, match="missing required fields"):
            RouterOutput(data)

    def test_router_output_reasoning_default(self) -> None:
        """Test RouterOutput reasoning defaults to empty string."""
        data = {
            "route": "sql",
            "query_type": "PERSONAL_FINANCIAL",
            "requires_cloud": False,
            "requires_tools": False,
        }
        output = RouterOutput(data)
        assert output.reasoning == ""


# =============================================================================
# Parser Tests
# =============================================================================

class TestParseRouterResponse:
    """Tests for the response parser."""

    def test_parse_valid_json(self) -> None:
        """Test parsing valid JSON response."""
        response = '{"query_type": "PERSONAL_FINANCIAL", "route": "sql", "requires_cloud": false, "requires_tools": false}'
        result = _parse_router_response(response)

        assert result["query_type"] == "PERSONAL_FINANCIAL"
        assert result["route"] == "sql"
        assert result["requires_cloud"] is False
        assert result["requires_tools"] is False

    def test_parse_json_with_markdown(self) -> None:
        """Test parsing JSON wrapped in markdown code blocks."""
        response = "```json\n{\"query_type\": \"RESEARCH\", \"route\": \"research\", \"requires_cloud\": false, \"requires_tools\": true}\n```"
        result = _parse_router_response(response)

        assert result["query_type"] == "RESEARCH"
        assert result["route"] == "research"
        assert result["requires_tools"] is True

    def test_parse_missing_fields(self) -> None:
        """Test parsing raises KeyError for missing required fields."""
        response = '{"query_type": "PERSONAL_FINANCIAL"}'  # Missing route, requires_cloud, requires_tools

        with pytest.raises(KeyError, match="missing fields"):
            _parse_router_response(response)

    def test_parse_invalid_json(self) -> None:
        """Test parsing raises JSONDecodeError for invalid JSON."""
        response = "not valid json {"

        with pytest.raises(json.JSONDecodeError):
            _parse_router_response(response)


# =============================================================================
# Heuristic Router Tests
# =============================================================================

class TestHeuristicRouter:
    """Tests for the heuristic fallback router."""

    @pytest.mark.parametrize(
        "query,expected_type",
        [
            # RESEARCH queries
            ("¿Cuál es la inflación hoy?", QueryType.RESEARCH),
            ("Busca las últimas noticias del BCRA", QueryType.RESEARCH),
            ("¿Tipo de cambio actual?", QueryType.RESEARCH),
            ("Noticias sobre el dólar", QueryType.RESEARCH),

            # PERSONAL_FINANCIAL queries
            ("¿Cuál es mi patrimonio?", QueryType.PERSONAL_FINANCIAL),
            ("¿Cuánto gasté el mes pasado?", QueryType.PERSONAL_FINANCIAL),
            ("Muestra mis ingresos", QueryType.PERSONAL_FINANCIAL),
            ("¿Cuánto tengo en la cuenta?", QueryType.PERSONAL_FINANCIAL),

            # HYBRID queries
            ("¿Debería comprar acciones con mi patrimonio?", QueryType.HYBRID),
            ("¿Puedo permitirme invertir con mis gastos?", QueryType.HYBRID),
            ("Dado mi situación, ¿conviene ahorrar?", QueryType.HYBRID),

            # MARKET_KNOWLEDGE queries
            ("¿Qué es un CEDEAR?", QueryType.MARKET_KNOWLEDGE),
            ("Explicame el dólar MEP", QueryType.MARKET_KNOWLEDGE),
            ("¿Qué es el impuesto a las ganancias?", QueryType.MARKET_KNOWLEDGE),

            # GENERAL_FINANCE queries (default)
            ("¿Qué es el interés compuesto?", QueryType.GENERAL_FINANCE),
            ("Explicame la regla del 72", QueryType.GENERAL_FINANCE),
        ],
    )
    def test_heuristic_classification(self, query: str, expected_type: QueryType) -> None:
        """Test heuristic router correctly classifies queries."""
        result = _heuristic_router(query)

        assert result.query_type == expected_type
        assert result.route == QUERY_TYPE_CONFIG[expected_type]["route"]
        assert result.requires_cloud == QUERY_TYPE_CONFIG[expected_type]["requires_cloud"]
        assert result.requires_tools == QUERY_TYPE_CONFIG[expected_type]["requires_tools"]

    def test_heuristic_returns_valid_router_output(self) -> None:
        """Test heuristic router returns valid RouterOutput."""
        result = _heuristic_router("¿Cuál es mi patrimonio?")

        assert isinstance(result, RouterOutput)
        assert "route" in result
        assert "query_type" in result
        assert "requires_cloud" in result
        assert "requires_tools" in result
        assert "reasoning" in result


# =============================================================================
# Router Node Tests (with mocked llama.cpp)
# =============================================================================

class TestRouterNode:
    """Tests for the router node with mocked llama.cpp responses."""

    @pytest.mark.parametrize(
        "query,expected_type,expected_route,requires_cloud,requires_tools",
        TEST_QUERIES,
    )
    @pytest.mark.asyncio
    async def test_router_classifies_queries(
        self,
        query: str,
        expected_type: QueryType,
        expected_route: str,
        requires_cloud: bool,
        requires_tools: bool,
    ) -> None:
        """Test router correctly classifies all test queries."""
        # Mock llama.cpp response
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "query_type": expected_type,
                            "route": expected_route,
                            "requires_cloud": requires_cloud,
                            "requires_tools": requires_tools,
                            "reasoning": "Mocked classification",
                        })
                    }
                }
            ]
        }

        mock_post = AsyncMock(return_value=AsyncMock(json=lambda: mock_response, raise_for_status=lambda: None))

        with patch("httpx.AsyncClient", return_value=AsyncMock(post=mock_post)):
            state = {"query": query}
            result = await router_node(state)

        # router_node returns {"router_output": RouterOutput(...)}
        router_output = result.get("router_output")
        assert router_output is not None
        assert router_output.query_type == expected_type
        assert router_output.route == expected_route
        assert router_output.requires_cloud == requires_cloud
        assert router_output.requires_tools == requires_tools

    @pytest.mark.asyncio
    async def test_router_fallback_on_server_error(self) -> None:
        """Test router falls back to heuristic on server error."""
        with patch("httpx.AsyncClient", return_value=AsyncMock(
            post=AsyncMock(side_effect=httpx.RequestError("Server unavailable"))
        )):
            state = {"query": "¿Cuál es mi patrimonio?"}
            result = await router_node(state)

        # Should fall back to heuristic router
        router_output = result.get("router_output")
        assert router_output is not None
        assert router_output.query_type == QueryType.PERSONAL_FINANCIAL
        assert "Heuristic" in router_output.reasoning

    @pytest.mark.asyncio
    async def test_router_fallback_on_parse_error(self) -> None:
        """Test router falls back to heuristic on parse error."""
        mock_response = {
            "choices": [{"message": {"content": "not valid json"}}]
        }

        with patch("httpx.AsyncClient", return_value=AsyncMock(
            post=AsyncMock(return_value=AsyncMock(json=lambda: mock_response, raise_for_status=lambda: None))
        )):
            state = {"query": "¿Cuál es mi patrimonio?"}
            result = await router_node(state)

        # Should fall back to heuristic router
        router_output = result.get("router_output")
        assert router_output is not None
        assert router_output.query_type == QueryType.PERSONAL_FINANCIAL
        assert "Heuristic" in router_output.reasoning

    @pytest.mark.asyncio
    async def test_router_low_temperature(self) -> None:
        """Test router uses low temperature for deterministic classification."""
        mock_response = {
            "choices": [{"message": {"content": '{"query_type": "GENERAL_FINANCE", "route": "general", "requires_cloud": false, "requires_tools": false}'}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(json=lambda: mock_response, raise_for_status=lambda: None))

        with patch("httpx.AsyncClient", return_value=mock_client):
            state = {"query": "Test query"}
            await router_node(state)

        # Verify temperature was set to 0.1
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["temperature"] == 0.1


# =============================================================================
# Query Type Config Tests
# =============================================================================

class TestQueryTypeConfig:
    """Tests for the query type configuration."""

    def test_all_query_types_have_config(self) -> None:
        """Test all query types have corresponding configuration."""
        query_types = [
            QueryType.PERSONAL_FINANCIAL,
            QueryType.MARKET_KNOWLEDGE,
            QueryType.HYBRID,
            QueryType.GENERAL_FINANCE,
            QueryType.RESEARCH,
        ]
        for query_type in query_types:
            assert query_type in QUERY_TYPE_CONFIG, f"Missing config for {query_type}"

    def test_config_has_required_fields(self) -> None:
        """Test each config has required fields."""
        required_fields = {"route", "requires_cloud", "requires_tools"}
        for query_type, config in QUERY_TYPE_CONFIG.items():
            missing = required_fields - set(config.keys())
            assert not missing, f"Config for {query_type} missing fields: {missing}"

    def test_route_values_are_valid(self) -> None:
        """Test route values are valid node names."""
        valid_routes = {"sql", "rag", "hybrid", "general", "research"}
        for query_type, config in QUERY_TYPE_CONFIG.items():
            assert config["route"] in valid_routes, f"Invalid route for {query_type}: {config['route']}"

    def test_hybrid_requires_cloud(self) -> None:
        """Test HYBRID query type requires cloud LLM."""
        assert QUERY_TYPE_CONFIG[QueryType("HYBRID")]["requires_cloud"] is True

    def test_research_requires_tools(self) -> None:
        """Test RESEARCH query type requires tools."""
        assert QUERY_TYPE_CONFIG[QueryType("RESEARCH")]["requires_tools"] is True

    def test_personal_financial_no_cloud_no_tools(self) -> None:
        """Test PERSONAL_FINANCIAL doesn't require cloud or tools."""
        config = QUERY_TYPE_CONFIG[QueryType("PERSONAL_FINANCIAL")]
        assert config["requires_cloud"] is False
        assert config["requires_tools"] is False


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestRouterEdgeCases:
    """Tests for router edge cases."""

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        """Test router handles empty query."""
        result = _heuristic_router("")
        assert result.query_type == QueryType.GENERAL_FINANCE  # Default

    @pytest.mark.asyncio
    async def test_very_long_query(self) -> None:
        """Test router handles very long query."""
        long_query = "¿ " * 1000 + "mi patrimonio?"
        result = _heuristic_router(long_query)
        assert result.query_type == QueryType.PERSONAL_FINANCIAL

    @pytest.mark.asyncio
    async def test_special_characters(self) -> None:
        """Test router handles special characters."""
        query = "¿Patrimonio $1,234,567.89 ARS + €500?"
        result = _heuristic_router(query)
        assert result.query_type == QueryType.PERSONAL_FINANCIAL

    @pytest.mark.asyncio
    async def test_mixed_language(self) -> None:
        """Test router handles mixed Spanish/English."""
        query = "What is my net worth / ¿Cuál es mi patrimonio?"
        result = _heuristic_router(query)
        # Should match "mi patrimonio" pattern
        assert result.query_type == QueryType.PERSONAL_FINANCIAL
