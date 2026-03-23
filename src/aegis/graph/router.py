# SPDX-License-Identifier: MIT
"""Router node for query classification using Qwen 3.5 via llama.cpp.

Classifies incoming user queries into one of five categories:
- PERSONAL_FINANCIAL: Questions about user's own financial data
- MARKET_KNOWLEDGE: Questions about financial concepts and Argentine market
- HYBRID: Questions requiring both personal data and market reasoning
- GENERAL_FINANCE: General financial education questions
- RESEARCH: Questions requiring current/real-time web information
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict, NotRequired
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# Type Definitions
# =============================================================================


class QueryType(str, Enum):
    """Enumeration of query types for classification."""

    PERSONAL_FINANCIAL = "PERSONAL_FINANCIAL"
    MARKET_KNOWLEDGE = "MARKET_KNOWLEDGE"
    HYBRID = "HYBRID"
    GENERAL_FINANCE = "GENERAL_FINANCE"
    RESEARCH = "RESEARCH"


class RouterOutputData(TypedDict, total=True):
    """TypedDict for router output data."""

    route: str
    query_type: str
    requires_cloud: bool
    requires_tools: bool
    reasoning: NotRequired[str]


class RouterOutput(dict[str, Any]):
    """Structured output from the router node.

    Attributes:
        route: Target flow name ("sql", "rag", "hybrid", "general", "research")
        query_type: Classification category (one of QueryType values)
        requires_cloud: Whether cloud LLM is needed for this query
        requires_tools: Whether web search/browser tools are needed
        reasoning: Brief explanation of the classification
    """

    def __init__(self, data: RouterOutputData) -> None:
        super().__init__(data)
        # Validate required fields
        required = {"route", "query_type", "requires_cloud", "requires_tools"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"RouterOutput missing required fields: {missing}")

    @property
    def route(self) -> str:
        return self["route"]

    @property
    def query_type(self) -> str:
        return self["query_type"]

    @property
    def requires_cloud(self) -> bool:
        return self["requires_cloud"]

    @property
    def requires_tools(self) -> bool:
        return self["requires_tools"]

    @property
    def reasoning(self) -> str:
        return self.get("reasoning", "")


# =============================================================================
# Router Configuration
# =============================================================================


class QueryTypeConfig(TypedDict):
    """Configuration for a query type."""

    route: str
    requires_cloud: bool
    requires_tools: bool


ROUTER_SYSTEM_PROMPT = """You are a query router for a personal finance assistant.
Classify the user's query into exactly one of these categories:

1. PERSONAL_FINANCIAL - Questions about the user's own financial data (net worth,
   spending, transactions, assets, income)

2. MARKET_KNOWLEDGE - Questions about financial concepts, instruments, or
   Argentine market mechanics (CEDEARs, MEP dollar, taxes)

3. HYBRID - Questions that require BOTH personal financial data AND market
   reasoning to answer (e.g., "Should I buy more stocks given my portfolio?")

4. GENERAL_FINANCE - General financial education questions not specific to
   Argentina or the user's personal situation

5. RESEARCH - Questions requiring current/real-time information from the web
   (today's inflation rate, latest BCRA news, current exchange rates)

Output ONLY valid JSON with this exact schema:
{{
  "query_type": "ONE_OF_THE_FIVE_CATEGORIES",
  "route": "sql" | "rag" | "hybrid" | "general" | "research",
  "requires_cloud": true | false,
  "requires_tools": true | false,
  "reasoning": "brief explanation"
}}

Query: {query}"""

# Mapping from query type to route and flags
QUERY_TYPE_CONFIG: dict[QueryType, QueryTypeConfig] = {
    QueryType.PERSONAL_FINANCIAL: {
        "route": "sql",
        "requires_cloud": False,
        "requires_tools": False,
    },
    QueryType.MARKET_KNOWLEDGE: {
        "route": "rag",
        "requires_cloud": False,
        "requires_tools": False,
    },
    QueryType.HYBRID: {
        "route": "hybrid",
        "requires_cloud": True,
        "requires_tools": False,
    },
    QueryType.GENERAL_FINANCE: {
        "route": "general",
        "requires_cloud": False,
        "requires_tools": False,
    },
    QueryType.RESEARCH: {
        "route": "research",
        "requires_cloud": False,
        "requires_tools": True,
    },
}


# =============================================================================
# Router Node Implementation
# =============================================================================


async def router_node(
    state: dict[str, Any], llama_cpp_url: str = "http://localhost:8080"
) -> dict[str, Any]:
    """Classify a user query and determine the appropriate processing route.

    Args:
        state: Current graph state containing the query.
        llama_cpp_url: Base URL of the llama.cpp inference server.

    Returns:
        Dict with ``router_output`` key containing classification results.

    Behavior:
        This function attempts to classify the query using a llama.cpp server.
        If the server is unavailable (e.g. an ``httpx.RequestError`` occurs) or
        the LLM response cannot be parsed (e.g. ``json.JSONDecodeError`` or
        missing keys), the error is logged and a heuristic-based fallback
        classification is used instead. Callers do not need to handle network
        or parsing exceptions raised during routing.
    """
    query = state.get("query", "")

    # Build the request payload
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT.format(query=query)},
        {"role": "user", "content": f"Classify this query: {query}"},
    ]

    try:
        response = await _call_llama_cpp(messages, llama_cpp_url)
        parsed = _parse_router_response(response)
        router_output = RouterOutput(parsed)

    except httpx.RequestError as e:
        logger.error("llama.cpp server unavailable: %s", e)
        # Fallback to simple heuristic-based classification
        router_output = _heuristic_router(query)

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(
            "Failed to parse router response: %s. Using heuristic fallback.", e
        )
        router_output = _heuristic_router(query)

    return {"router_output": router_output}


async def _call_llama_cpp(messages: list[dict[str, str]], url: str) -> str:
    """Call the llama.cpp chat completion endpoint.

    Args:
        messages: List of message dicts with "role" and "content" keys.
        url: Base URL of the llama.cpp server.

    Returns:
        The model's response text.
    """
    endpoint = f"{url}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": "qwen3.5",
        "messages": messages,
        "temperature": 0.1,  # Low temperature for deterministic classification
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return data["choices"][0]["message"]["content"]


def _parse_router_response(response_text: str) -> dict[str, Any]:
    """Parse the LLM's JSON response into a structured dict.

    Args:
        response_text: Raw response string from the LLM.

    Returns:
        Parsed dictionary with router output fields.

    Raises:
        json.JSONDecodeError: If response is not valid JSON.
        KeyError: If required fields are missing.
    """
    # Clean up any markdown code blocks
    cleaned = response_text.strip()

    # Remove opening markdown code block
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    # Remove closing markdown code block
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()

    # Try to find JSON object in the response
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}") + 1

    if start_idx >= 0 and end_idx > start_idx:
        cleaned = cleaned[start_idx:end_idx]

    parsed = json.loads(cleaned)

    # Validate that parsed result is a dict
    if not isinstance(parsed, dict):
        raise KeyError("Router response is not a JSON object")

    # Validate required fields
    required = {"query_type", "route", "requires_cloud", "requires_tools"}
    missing = required - set(parsed.keys())
    if missing:
        raise KeyError(f"Router response missing fields: {missing}")

    return parsed


def _heuristic_router(query: str) -> RouterOutput:
    """Fallback heuristic-based router when LLM is unavailable.

    Uses simple keyword matching and pattern detection for basic classification.

    Args:
        query: The user's query to classify.

    Returns:
        RouterOutput with heuristic-based classification.
    """
    query_lower = query.lower()

    # RESEARCH indicators - questions about current/real-time data
    research_keywords = [
        "hoy",
        "actualmente",
        "actual",
        "última",
        "últimas",
        "actualización",
        "tiempo real",
        "en vivo",
        "busca",
        "buscar",
        "noticias",
        "tasa de inflación",
        "tipo de cambio",
    ]
    for keyword in research_keywords:
        if keyword in query_lower:
            return RouterOutput(
                QUERY_TYPE_CONFIG[QueryType.RESEARCH]
                | {
                    "query_type": QueryType.RESEARCH,
                    "reasoning": "Heuristic: detected research keyword",
                }
            )

    # HYBRID indicators - combines personal + advice/reasoning
    # Check BEFORE personal finance to catch hybrid queries first
    hybrid_patterns = [
        ("debería", "mi"),
        ("debería", "mis"),
        ("debería", "gastos"),
        ("puedo", "mi"),
        ("puedo", "mis"),
        ("puedo", "gastos"),
        ("conviene", "mi"),
        ("recomienda", "mi"),
        ("dado mi", None),
        ("permitirme", None),  # "¿Puedo permitirme...?" is hybrid
    ]
    for pattern in hybrid_patterns:
        if pattern[0] in query_lower and (
            pattern[1] is None or pattern[1] in query_lower
        ):
            return RouterOutput(
                QUERY_TYPE_CONFIG[QueryType.HYBRID]
                | {
                    "query_type": QueryType.HYBRID,
                    "reasoning": "Heuristic: detected hybrid pattern",
                }
            )

    # PERSONAL_FINANCIAL indicators - questions about user's own data
    personal_keywords = [
        "mi patrimonio",
        "mis gastos",
        "mis ingresos",
        "mi cuenta",
        "mis activos",
        "mi saldo",
        "gasté",
        "gané",
        "tengo",
        "¿cuál es mi",
        "¿cuánto gasté",
        "¿cuánto tengo",
        "patrimonio",  # Standalone keyword
    ]
    for keyword in personal_keywords:
        if keyword in query_lower:
            return RouterOutput(
                QUERY_TYPE_CONFIG[QueryType.PERSONAL_FINANCIAL]
                | {
                    "query_type": QueryType.PERSONAL_FINANCIAL,
                    "reasoning": "Heuristic: detected personal finance keyword",
                }
            )

    # MARKET_KNOWLEDGE indicators - Argentine market concepts
    # Exclude generic terms like "qué es" and "explicame" - those are too broad
    market_keywords = [
        "cedear",
        "mep",
        "ccl",
        "dólar blue",
        "bcra",
        "byma",
        "aba",
        "impuesto a las ganancias",
        "monotributo",
        "afip",
    ]
    for keyword in market_keywords:
        if keyword in query_lower:
            return RouterOutput(
                QUERY_TYPE_CONFIG[QueryType.MARKET_KNOWLEDGE]
                | {
                    "query_type": QueryType.MARKET_KNOWLEDGE,
                    "reasoning": "Heuristic: detected market knowledge keyword",
                }
            )

    # Default to GENERAL_FINANCE
    return RouterOutput(
        QUERY_TYPE_CONFIG[QueryType.GENERAL_FINANCE]
        | {
            "query_type": QueryType.GENERAL_FINANCE,
            "reasoning": "Heuristic: default to general finance",
        }
    )
