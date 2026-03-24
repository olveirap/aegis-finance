# SPDX-License-Identifier: MIT
"""Research flow node for the LangGraph orchestrator.

Orchestrates the research process:
1. Redact query (Privacy Node)
2. Search web (Search Tool)
3. Browse relevant pages (Browser Tool)
4. Synthesize answer (Local LLM)
"""

from __future__ import annotations

import logging
from typing import Any

from aegis.graph.privacy import privacy_node
from aegis.tools.search import search_duckduckgo
from aegis.tools.browser import browse_url, is_whitelisted
from aegis.common.cloud_llm import CloudLLMClient
from aegis.config import get_config

logger = logging.getLogger(__name__)


async def research_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """Research flow node.

    Args:
        state: Current graph state.

    Returns:
        Updated state with research results and final answer.
    """
    # 1. Privacy Pass
    # We call privacy_node to get the sanitized query
    privacy_result = await privacy_node(state)

    # If privacy node returned a final_answer (blocked), we stop here
    if "final_answer" in privacy_result:
        return privacy_result

    privacy_output = privacy_result["privacy_output"]
    sanitized_query = privacy_output["sanitized_query"]

    # 2. Search
    search_results = await search_duckduckgo(sanitized_query)
    if not search_results:
        return {
            "final_answer": "I searched for information but couldn't find any relevant results."
        }

    # 3. Filter and Browse
    # Select top whitelisted results based on config
    max_pages = get_config().rag.research_max_pages
    browsed_content = []
    for res in search_results:
        url = res["href"]
        if is_whitelisted(url):
            content = await browse_url(url)
            if content:
                browsed_content.append(
                    {
                        "title": res["title"],
                        "url": url,
                        "content": content[:3000],  # Limit content size
                    }
                )
        if len(browsed_content) >= max_pages:
            break

    # 4. Synthesis
    context = ""
    if browsed_content:
        for c in browsed_content:
            context += f"Source: {c['title']} ({c['url']})\nContent: {c['content']}\n\n"
    else:
        # Use snippets if no whitelist pages could be browsed
        for res in search_results[:3]:
            context += (
                f"Source: {res['title']} ({res['href']})\nSnippet: {res['body']}\n\n"
            )

    final_answer = await _synthesize_research(sanitized_query, context)

    return {
        "privacy_output": privacy_output,
        "tool_results": search_results,
        "final_answer": final_answer,
    }


async def _synthesize_research(query: str, context: str) -> str:
    """Synthesize research findings using the cloud client (with local fallback)."""
    cloud_client = CloudLLMClient()

    system_prompt = """You are a financial research assistant.
Based on the following search results and browsed content, answer the user's query.
The user's query has been anonymized for privacy.
Be objective, cite your sources, and focus on the Argentine financial market context if applicable."""

    user_prompt = f"Query: {query}\n\nResearch Context:\n{context}\n\nPlease provide a comprehensive answer."

    try:
        return await cloud_client.generate(system_prompt, user_prompt, temperature=0.3)
    except Exception as e:
        logger.error("Synthesis failed: %s", e)
        return f"I found the following information, but I encountered an error while synthesizing the final answer:\n\n{context[:500]}..."
