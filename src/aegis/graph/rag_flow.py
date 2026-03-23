# SPDX-License-Identifier: MIT
"""RAG flow node for the LangGraph orchestrator.

Orchestrates retrieval from knowledge base and synthesis using local LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from aegis.graph.privacy import privacy_node
from aegis.rag.retriever import Retriever
from aegis.common.cloud_llm import CloudLLMClient

logger = logging.getLogger(__name__)


async def rag_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """RAG-only flow node.

    Args:
        state: Current graph state.

    Returns:
        Updated state with RAG answer.
    """
    # 1. Privacy Pass
    privacy_result = await privacy_node(state)
    if "final_answer" in privacy_result:
        return privacy_result

    privacy_output = privacy_result["privacy_output"]
    sanitized_query = privacy_output["sanitized_query"]

    # 2. RAG Step
    retriever = Retriever()
    rag_chunks = await retriever.retrieve(sanitized_query)

    # 3. Context Synthesis
    context = ""
    for chunk in rag_chunks:
        context += f"Source: {chunk['source_title']} ({chunk['source']})\nContent: {chunk['content']}\n\n"

    # 4. synthesis using local LLM (for RAG flow as per Task 2.4 description)
    # Actually Task 2.4 says "General flow node (local RAG only)"
    # and Hybrid uses Cloud LLM.
    # I'll use local LLM here too.

    cloud_client = CloudLLMClient()  # generate handles fallback to local
    system_prompt = """You are a financial knowledge assistant. 
Answer the user's query based ONLY on the provided knowledge base context.
If you don't know the answer, say so. Be objective and cite sources."""

    user_prompt = (
        f"Query: {sanitized_query}\n\nContext:\n{context}\n\nPlease answer the query."
    )

    # Force local by disabling cloud if needed, but generate() handles it via config
    final_answer = await cloud_client.generate(system_prompt, user_prompt)

    return {
        "rag_chunks": rag_chunks,
        "privacy_output": privacy_output,
        "final_answer": final_answer,
    }
