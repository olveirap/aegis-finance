# SPDX-License-Identifier: MIT
"""Staleness guardrail node for the LangGraph orchestrator.

Detects if transaction data or exchange rates are older than the configured
threshold and attaches a warning to the state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from aegis.config import get_config
from aegis.db.connection import get_connection

logger = logging.getLogger(__name__)


async def check_staleness() -> str | None:
    """Query the database to check for stale data.

    Returns:
        A warning string if data is stale, else None.
    """
    config = get_config().staleness
    threshold_days = config.warn_after_days
    now = datetime.now(timezone.utc)
    
    warnings = []
    
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                # 1. Check last import
                await cur.execute("SELECT MAX(imported_at) FROM import_batches")
                row = await cur.fetchone()
                last_import = row[0] if row and row[0] else None
                
                if last_import:
                    # Convert to UTC if offset-naive
                    if last_import.tzinfo is None:
                        last_import = last_import.replace(tzinfo=timezone.utc)
                    
                    diff = (now - last_import).days
                    if diff > threshold_days:
                        warnings.append(f"Transactions are {diff} days old.")
                else:
                    warnings.append("No transaction data imported yet.")

                # 2. Check last exchange rate fetch
                await cur.execute("SELECT MAX(fetched_at) FROM exchange_rates")
                row = await cur.fetchone()
                last_fx = row[0] if row and row[0] else None
                
                if last_fx:
                    if last_fx.tzinfo is None:
                        last_fx = last_fx.replace(tzinfo=timezone.utc)
                        
                    diff = (now - last_fx).days
                    if diff > 1: # FX is usually stale after 1 day
                        warnings.append(f"Exchange rates are {diff} days old.")
                else:
                    warnings.append("No exchange rates available.")

    except Exception as e:
        logger.error("Failed to check staleness: %s", e)
        # We don't want to block the flow on a check failure, but we log it
        return None

    if warnings:
        msg = "[STALE_DATA_WARNING] " + " ".join(warnings)
        return msg
        
    return None


async def staleness_node(state: dict[str, Any]) -> dict[str, Any]:
    """Staleness guardrail node.

    Args:
        state: Current graph state.

    Returns:
        Updated state with warnings attached to final_answer.
    """
    warning = await check_staleness()
    
    if not warning:
        return {} # No changes
        
    final_answer = state.get("final_answer", "")
    if final_answer:
        # Prepend warning to existing answer
        return {"final_answer": f"{warning}\n\n{final_answer}"}
    
    # If no final answer yet (unlikely if node is at the end), we can just set it
    # but normally we want to prepend.
    return {"final_answer": warning}
