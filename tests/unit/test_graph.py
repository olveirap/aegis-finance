# SPDX-License-Identifier: MIT
"""Unit tests for the Aegis Finance LangGraph orchestrator.

Tests routing decisions, graph structure, and fallback behavior.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.graph.state import CompiledStateGraph

from aegis.graph import create_aegis_graph, route_query


# =============================================================================
# route_query Tests
# =============================================================================


class TestRouteQuery:
    """Tests for the conditional edge routing logic."""

    @pytest.mark.parametrize(
        "route_value,expected_node",
        [
            ("sql", "sql_flow"),
            ("rag", "rag_flow"),
            ("hybrid", "hybrid_flow"),
            ("general", "general_flow"),
            ("research", "research_flow"),
        ],
    )
    def test_route_query_valid_routes(
        self, route_value: str, expected_node: str
    ) -> None:
        """Test routing for all known valid route values."""
        state = {"router_output": {"route": route_value}}
        assert route_query(state) == expected_node

    def test_route_query_missing_router_output(self) -> None:
        """Test fallback when router_output is missing from state."""
        state: dict[str, Any] = {}
        assert route_query(state) == "general_flow"

    def test_route_query_missing_route_field(self) -> None:
        """Test fallback when route field is missing from router_output."""
        state = {"router_output": {}}
        assert route_query(state) == "general_flow"

    def test_route_query_unknown_route(self) -> None:
        """Test fallback when router returns an unknown route string."""
        state = {"router_output": {"route": "unknown_destination"}}
        assert route_query(state) == "general_flow"

    def test_route_query_none_router_output(self) -> None:
        """Test fallback when router_output is explicitly None."""
        state = {"router_output": None}
        assert route_query(state) == "general_flow"


# =============================================================================
# Graph Structure Tests
# =============================================================================


class TestGraphStructure:
    """Tests for the Aegis graph construction."""

    def test_create_aegis_graph_returns_compiled_graph(self) -> None:
        """Verify the graph is created and can be compiled."""
        graph = create_aegis_graph()
        compiled_graph = graph.compile()
        assert isinstance(compiled_graph, CompiledStateGraph)

    def test_graph_has_expected_nodes(self) -> None:
        """Verify all required nodes are present in the graph."""
        graph = create_aegis_graph()
        # Accessing internal nodes attribute of StateGraph
        nodes = graph.nodes

        expected_nodes = {
            "router",
            "sql_flow",
            "rag_flow",
            "hybrid_flow",
            "general_flow",
            "research_flow",
        }

        for node in expected_nodes:
            assert node in nodes, f"Node {node} missing from graph"
