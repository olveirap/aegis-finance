# SPDX-License-Identifier: MIT
"""General flow node for the LangGraph orchestrator.

Handles general financial questions using local RAG.
"""

from __future__ import annotations

import logging
from typing import Any

from aegis.graph.rag_flow import rag_flow_node

logger = logging.getLogger(__name__)


async def general_flow_node(state: dict[str, Any]) -> dict[str, Any]:
    """General flow node.

    Delegates to rag_flow_node for now as they share the same local RAG logic.
    """
    return await rag_flow_node(state)
