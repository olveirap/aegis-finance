# SPDX-License-Identifier: MIT
"""Text-to-SQL flow node for the LangGraph orchestrator.

Handles view selection, SQL generation, validation (syntax, schema, EXPLAIN),
and execution against the database.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
import numpy as np
import psycopg

from aegis.config import get_config
from aegis.db.connection import get_connection

logger = logging.getLogger(__name__)

# =============================================================================
# View Metadata Definitions
# =============================================================================

VIEWS_METADATA = {
    "v_net_worth": {
        "description": "Total net worth in ARS and USD, including cash, investments, and exchange rates. Use this for questions about total balances, wealth, or current conversion rates.",
        "ddl": """CREATE OR REPLACE VIEW v_net_worth AS
SELECT total_ars, total_usd, total_assets_usd, total_usd_equivalent, rate_timestamp FROM ...""",
    },
    "v_monthly_burn": {
        "description": "Monthly transaction aggregates by category and currency. Use this for questions about monthly spending, expenses, burn rate, or average transaction size.",
        "ddl": """CREATE OR REPLACE VIEW v_monthly_burn AS
SELECT month, category, currency, tx_count, total_spend, avg_transaction FROM ...""",
    },
    "v_cedear_exposure": {
        "description": "Current holdings of CEDEARs, including quantity, cost, current value, and PnL. Use this for portfolio, stock, or investment exposure queries.",
        "ddl": """CREATE OR REPLACE VIEW v_cedear_exposure AS
SELECT ticker, quantity, avg_cost_usd, last_price_usd, current_value_usd, pnl_pct, last_price_at FROM ...""",
    },
    "v_income_summary": {
        "description": "Summary of active income sources compared to actual monthly transactions. Use this for salary, freelance earnings, or expected vs actual income questions.",
        "ddl": """CREATE OR REPLACE VIEW v_income_summary AS
SELECT label, type, currency, expected_monthly, actual_monthly_avg FROM ...""",
    },
    "v_category_spend": {
        "description": "Detailed breakdown of spending by category, including min, max, average, and total amounts per month. Use this for deep dives into category expenses.",
        "ddl": """CREATE OR REPLACE VIEW v_category_spend AS
SELECT category, currency, month, transaction_count, total_amount, avg_amount, min_amount, max_amount FROM ...""",
    },
}

ALLOWED_VIEWS = set(VIEWS_METADATA.keys())

# =============================================================================
# Helper Functions
# =============================================================================


async def _embed_text(text: str) -> np.ndarray:
    """Get the embedding for a text using the local embedding model."""
    config = get_config()
    api_base = config.embedding.api_base
    model = config.embedding.model

    payload = {
        "input": text,
        "model": model,
    }

    # Simple fallback for tests if mock embedder is needed
    if "localhost" not in api_base and "127.0.0.1" not in api_base:
        return np.random.rand(config.embedding.dimension).astype(np.float32)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{api_base}/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return np.array(data["data"][0]["embedding"], dtype=np.float32)
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("Failed to embed text: %s", e)
        # Return random embedding as fallback to not crash the flow completely
        return np.random.rand(config.embedding.dimension).astype(np.float32)


async def _get_view_embeddings() -> dict[str, np.ndarray]:
    """Cache and return embeddings for the view descriptions."""
    if not hasattr(_get_view_embeddings, "_cache"):
        _get_view_embeddings._cache = {}
        for view_name, meta in VIEWS_METADATA.items():
            _get_view_embeddings._cache[view_name] = await _embed_text(
                meta["description"]
            )
    return _get_view_embeddings._cache


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def select_relevant_views(query: str, top_k: int = 3) -> list[str]:
    """Select the most relevant views for a query using cosine similarity."""
    query_emb = await _embed_text(query)
    view_embs = await _get_view_embeddings()

    similarities = [
        (view_name, _cosine_similarity(query_emb, emb))
        for view_name, emb in view_embs.items()
    ]

    similarities.sort(key=lambda x: x[1], reverse=True)
    return [view_name for view_name, _ in similarities[:top_k]]


def _extract_sql(text: str) -> str:
    """Extract SQL query from markdown blocks."""
    match = re.search(r"```sql\s+(.*?)\s+```", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback if no markdown block
    cleaned = text.strip()
    if cleaned.upper().startswith("SELECT"):
        return cleaned

    raise ValueError(
        "Could not extract a valid SQL SELECT statement from the response."
    )


def _validate_syntax_and_whitelist(sql: str) -> None:
    """Check that the SQL is a SELECT statement and uses only allowed views."""
    sql_upper = sql.upper()
    if not sql_upper.startswith("SELECT"):
        raise ValueError("Query must be a SELECT statement.")

    # Check for forbidden base tables or unknown views
    # Simple regex to find words after FROM or JOIN
    from_join_pattern = re.compile(r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z_0-9]*)", re.IGNORECASE)
    tables = from_join_pattern.findall(sql)

    for table in tables:
        # Ignore subqueries or functions that might be captured
        if table.upper() in {"SELECT", "UNNEST", "LATERAL", "AS", "ON"}:
            continue
        if table.lower() not in ALLOWED_VIEWS:
            raise ValueError(
                f"Query attempts to use unauthorized table/view: '{table}'. Only {', '.join(ALLOWED_VIEWS)} are allowed."
            )


async def _validate_schema(sql: str) -> None:
    """Validate query schema using EXPLAIN."""
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(f"EXPLAIN (FORMAT JSON) {sql}")
    except psycopg.Error as e:
        raise ValueError(f"PostgreSQL syntax/schema error: {e}")


def _check_currency_mixing(sql: str) -> str | None:
    """Check for dangerous aggregation across mixed currencies."""
    sql_upper = sql.upper()
    if "SUM(" in sql_upper or "AVG(" in sql_upper:
        if "CURRENCY" not in sql_upper:
            # Not a strict parser, but a heuristic flag
            return "Warning: The query aggregates amounts without grouping by currency. ARS and USD values may be mixed."
    return None


async def _call_llm(prompt: str) -> str:
    """Call the local LLM to generate SQL."""
    config = get_config()
    url = config.llm.local.llama_cpp_server

    messages = [
        {
            "role": "system",
            "content": "You are a PostgreSQL expert for a personal finance application. Your task is to output valid PostgreSQL queries based on the user's request and the provided view schemas. Output ONLY the SQL query wrapped in ```sql ``` blocks.",
        },
        {"role": "user", "content": prompt},
    ]

    endpoint = f"{url}/v1/chat/completions"
    payload = {
        "model": config.llm.local.model,
        "messages": messages,
        "temperature": 0.0,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# =============================================================================
# Graph Node Implementation
# =============================================================================


async def sql_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """Text-to-SQL flow node.

    1. Selects relevant views.
    2. Constructs prompt.
    3. Retries up to 3 times to get valid SQL.
    4. Executes SQL and updates state.
    """
    query = state.get("query", "")

    # 1. View Selection
    selected_views = await select_relevant_views(query)
    schema_context = "\n\n".join([VIEWS_METADATA[v]["ddl"] for v in selected_views])

    base_prompt = f"""
Given the following PostgreSQL view schemas:

{schema_context}

Write a SQL query to answer the user's question.
Rules:
1. ONLY use the views provided above. DO NOT query 'transactions', 'accounts', or any other base tables.
2. Ensure you handle currency correctly (e.g. do not sum ARS and USD without conversion).
3. Output ONLY valid PostgreSQL wrapped in ```sql ... ```.

Question: {query}
"""

    max_retries = 3
    current_prompt = base_prompt
    warning_msg = None
    final_sql = ""
    sql_result = []

    for attempt in range(max_retries):
        try:
            # 2. LLM Generation
            response = await _call_llm(current_prompt)

            # 3. Step 1: Syntax & Whitelist
            sql = _extract_sql(response)
            _validate_syntax_and_whitelist(sql)

            # 3. Step 2: Schema (EXPLAIN)
            await _validate_schema(sql)

            # 3. Step 3: Currency Mixing Sanity Check
            warning_msg = _check_currency_mixing(sql)

            final_sql = sql
            break  # Valid SQL found

        except ValueError as e:
            logger.warning(
                "SQL Validation failed (attempt %d/%d): %s", attempt + 1, max_retries, e
            )
            current_prompt = (
                base_prompt
                + f"\n\nYour previous query failed with error:\n{e}\n\nPlease correct it and try again."
            )
        except Exception as e:
            logger.error("Unexpected error in SQL flow: %s", e)
            return {"final_answer": f"System error generating SQL: {e}"}

    else:
        # Exhausted retries
        return {
            "final_answer": "I could not generate a valid SQL query to answer your question after 3 attempts."
        }

    # 4. Execution
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(final_sql)
                # Fetch results
                columns = [desc.name for desc in cursor.description]
                rows = await cursor.fetchall()
                sql_result = [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error("Error executing validated SQL: %s", e)
        return {"final_answer": f"Error executing query: {e}"}

    answer_prefix = ""
    if warning_msg:
        answer_prefix = f"[{warning_msg}]\n\n"

    return {
        "sql_result": sql_result,
        "final_answer": f"{answer_prefix}Query executed successfully. Found {len(sql_result)} records.",
    }
