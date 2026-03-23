# SPDX-License-Identifier: MIT
"""Privacy-preserving search tool using DuckDuckGo.

Uses DuckDuckGo to search the web using anonymized queries.
"""

from __future__ import annotations

import logging

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


async def search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo with an anonymized query.

    Args:
        query: The sanitized search query.
        max_results: Maximum number of search results to return.

    Returns:
        List of result dictionaries with 'title', 'href', and 'body'.
    """
    logger.info("Searching DuckDuckGo for: %s", query)

    results = []
    try:
        with DDGS() as ddgs:
            ddgs_results = ddgs.text(query, max_results=max_results)
            for r in ddgs_results:
                results.append(
                    {
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", ""),
                    }
                )
    except Exception as e:
        logger.error("DuckDuckGo search failed: %s", e)

    return results
