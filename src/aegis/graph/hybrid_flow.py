# SPDX-License-Identifier: MIT
"""Hybrid RAG flow node for the LangGraph orchestrator.

Orchestrates the process of combining SQL results, vector search results,
and cloud LLM synthesis with privacy protection.
"""

from __future__ import annotations

import logging
from typing import Any

from aegis.graph.sql_flow import sql_flow_node
from aegis.graph.privacy import privacy_node
from aegis.rag.retriever import Retriever
from aegis.common.cloud_llm import CloudLLMClient
from aegis.privacy.redaction_map import RedactionMap

logger = logging.getLogger(__name__)


async def hybrid_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """Hybrid flow node (SQL + Privacy + RAG + Cloud LLM).

    Args:
        state: Current graph state.

    Returns:
        Updated state with hybrid answer.
    """
    # 1. SQL Step
    sql_result_state = await sql_flow_node(state)
    if (
        "final_answer" in sql_result_state
        and "records" not in sql_result_state["final_answer"]
    ):
        # If SQL failed critically, we might still want to try RAG, but for now we follow sequential
        pass

    # Merge SQL results into state for privacy pass
    current_state = {**state, **sql_result_state}

    # 2. Privacy Pass
    privacy_result = await privacy_node(current_state)
    if "final_answer" in privacy_result:
        return privacy_result

    privacy_output = privacy_result["privacy_output"]
    sanitized_query = privacy_output["sanitized_query"]
    sanitized_context_sql = privacy_output["sanitized_context"]
    redaction_map_dict = privacy_output["redaction_map"]

    # 3. RAG Step
    retriever = Retriever()
    rag_chunks = await retriever.retrieve(sanitized_query)

    # 4. Context Synthesis
    rag_context = ""
    for chunk in rag_chunks:
        rag_context += f"Source: {chunk['source_title']} ({chunk['source']})\nContent: {chunk['content']}\n\n"

    master_context = f"""
USER FINANCIAL DATA (Anonymized):
{sanitized_context_sql}

RELEVANT FINANCIAL KNOWLEDGE:
{rag_context}
"""

    # 5. Cloud LLM Call
    cloud_client = CloudLLMClient()
    system_prompt = """You are a senior personal finance advisor. 
Analyze the user's financial data and the provided market knowledge to give professional, 
privacy-conscious advice. The data is anonymized; use the tokens (e.g. [PERSON_1]) as provided.
Speak clearly, be objective, and focus on the Argentine context."""

    user_prompt = f"Query: {sanitized_query}\n\nContext:\n{master_context}\n\nPlease provide your analysis."

    raw_answer = await cloud_client.generate(system_prompt, user_prompt)

    # 6. Reconstruction
    redaction_map = RedactionMap.from_dict(redaction_map_dict)
    final_answer = redaction_map.reconstruct(raw_answer)

    return {
        "sql_result": current_state.get("sql_result", []),
        "rag_chunks": rag_chunks,
        "privacy_output": privacy_output,
        "final_answer": final_answer,
    }
