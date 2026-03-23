# SPDX-License-Identifier: MIT
"""LangGraph orchestrator for Aegis Finance.

Provides the main state machine with router node and conditional routing
to different processing flows (SQL, RAG, Hybrid, General, Research).
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from aegis.graph.router import RouterOutput, router_node


# =============================================================================
# State Schema
# =============================================================================


class PrivacyOutput(TypedDict, total=False):
    """Output from the privacy middleware node.

    Attributes:
        sanitized_query: Query with PII redacted
        sanitized_context: Context with PII redacted
        redaction_map: Mapping of redaction tokens to original values
        risk_score: Residual PII risk score (0.0-1.0)
    """

    sanitized_query: str
    sanitized_context: str
    redaction_map: dict[str, Any]
    risk_score: float


class AegisState(TypedDict, total=False):
    """State schema for the Aegis Finance LangGraph orchestrator.

    This state is passed through all nodes in the graph and accumulates
    results from each processing step.

    Attributes:
        query: Original user query
        history: Conversation history as list of {role, content} dicts
        router_output: Router classification result
        sql_result: SQL query results (list of dicts)
        rag_chunks: Retrieved knowledge chunks
        privacy_output: Privacy middleware output
        tool_results: Results from tool executions
        final_answer: Final synthesized response
    """

    query: str
    history: list[dict[str, str]]
    router_output: RouterOutput
    sql_result: list[dict[str, Any]]
    rag_chunks: list[dict[str, Any]]
    privacy_output: PrivacyOutput
    tool_results: list[dict[str, Any]]
    final_answer: str


# =============================================================================
# Placeholder Nodes (to be implemented in subsequent tasks)
# =============================================================================


async def sql_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """Text-to-SQL flow node.

    To be implemented in Task 2.2.
    """
    # Placeholder - returns state unchanged
    return {"final_answer": "[SQL Flow not yet implemented]"}


async def rag_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """RAG retrieval flow node.

    To be implemented in Task 2.4.
    """
    # Placeholder - returns state unchanged
    return {"final_answer": "[RAG Flow not yet implemented]"}


async def hybrid_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """Hybrid flow node (SQL + Privacy + Cloud LLM).

    To be implemented across Tasks 2.2, 2.3, and 2.4.
    """
    # Placeholder - returns state unchanged
    return {"final_answer": "[Hybrid Flow not yet implemented]"}


async def general_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """General finance flow node (local RAG only).

    To be implemented in Task 2.4.
    """
    # Placeholder - returns state unchanged
    return {"final_answer": "[General Flow not yet implemented]"}


async def research_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """Research flow node (Privacy + Tools + Synthesis).

    To be implemented in Task 2.3b.
    """
    # Placeholder - returns state unchanged
    return {"final_answer": "[Research Flow not yet implemented]"}


# =============================================================================
# Conditional Edge Functions
# =============================================================================


def route_query(state: dict[str, Any]) -> str:
    """Conditional edge function to route queries to appropriate flow.

    Args:
        state: Current graph state containing router_output.

    Returns:
        Target node name based on router classification.
    """
    router_output = state.get("router_output")
    if router_output is None:
        # Default to general flow if no routing info
        return "general_flow"

    route = router_output.get("route", "general")

    route_mapping = {
        "sql": "sql_flow",
        "rag": "rag_flow",
        "hybrid": "hybrid_flow",
        "general": "general_flow",
        "research": "research_flow",
    }

    return route_mapping.get(route, "general_flow")


# =============================================================================
# Graph Builder
# =============================================================================


def create_aegis_graph() -> StateGraph:
    """Build and return the main Aegis Finance LangGraph state machine.

    Returns:
        Configured StateGraph ready for compilation.
    """
    graph = StateGraph(AegisState)

    # Add nodes
    graph.add_node("router", router_node)
    graph.add_node("sql_flow", sql_flow_node)
    graph.add_node("rag_flow", rag_flow_node)
    graph.add_node("hybrid_flow", hybrid_flow_node)
    graph.add_node("general_flow", general_flow_node)
    graph.add_node("research_flow", research_flow_node)

    # Set entry point
    graph.set_entry_point("router")

    # Add conditional edge from router to appropriate flow
    graph.add_conditional_edges(
        "router",
        route_query,
        {
            "sql_flow": "sql_flow",
            "rag_flow": "rag_flow",
            "hybrid_flow": "hybrid_flow",
            "general_flow": "general_flow",
            "research_flow": "research_flow",
        },
    )

    # All flows end at END
    graph.add_edge("sql_flow", END)
    graph.add_edge("rag_flow", END)
    graph.add_edge("hybrid_flow", END)
    graph.add_edge("general_flow", END)
    graph.add_edge("research_flow", END)

    return graph


# =============================================================================
# Compiled Graph Instance
# =============================================================================

# Create the compiled graph instance
aegis_graph = create_aegis_graph().compile()


# =============================================================================
# Convenience Functions
# =============================================================================


async def process_query(
    query: str, history: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    """Process a user query through the Aegis graph.

    Args:
        query: The user's natural language query.
        history: Optional conversation history.

    Returns:
        Final state containing the processed result.
    """
    initial_state = AegisState(
        {
            "query": query,
            "history": history or [],
        }
    )

    result = await aegis_graph.ainvoke(initial_state)
    return dict(result)
