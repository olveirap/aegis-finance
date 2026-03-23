# SPDX-License-Identifier: MIT
"""Privacy middleware node for the LangGraph orchestrator.

Orchestrates the multi-pass scrubbing pipeline (Regex -> Semantic -> Risk Scoring)
to ensure PII is redacted before leaving the local environment.
"""

from __future__ import annotations

import logging
from typing import Any

from aegis.config import get_config
from aegis.privacy.redaction_map import RedactionMap
from aegis.privacy.regex_scrubber import RegexScrubber
from aegis.privacy.semantic_scrubber import SemanticScrubber
from aegis.privacy.risk_scorer import RiskScorer

logger = logging.getLogger(__name__)

# Global instances for reuse (expensive to initialize)
_REGEX_SCRUBBER = RegexScrubber()
_SEMANTIC_SCRUBBER = SemanticScrubber()
_RISK_SCORER = RiskScorer()


async def privacy_node(state: dict[str, Any]) -> dict[str, Any]:
    """Privacy middleware node.

    1. Redacts sensitive information from the query.
    2. Redacts sensitive information from any context (SQL results, etc.) if present.
    3. Calculates a residual risk score.
    4. Blocks execution if risk is too high.
    """
    query = state.get("query", "")
    sql_result = state.get("sql_result", [])

    redaction_map = RedactionMap()

    # 1. Regex Pass
    scrubbed_query = _REGEX_SCRUBBER.scrub(query, redaction_map)

    # 2. Semantic Pass (Audit)
    scrubbed_query = await _SEMANTIC_SCRUBBER.scrub(scrubbed_query, redaction_map)

    # 3. Process Context (SQL Results)
    # We redact the values in the SQL result dictionaries
    sanitized_sql_result = []
    if sql_result:
        for row in sql_result:
            new_row = {}
            for k, v in row.items():
                if isinstance(v, str):
                    scrubbed_v = _REGEX_SCRUBBER.scrub(v, redaction_map)
                    # We don't necessarily need semantic pass for data that's already structured,
                    # but regex is good for catching leaked IDs in fields.
                    new_row[k] = scrubbed_v
                else:
                    new_row[k] = v
            sanitized_sql_result.append(new_row)

    # 4. Risk Scoring
    risk_score = _RISK_SCORER.calculate_risk(
        scrubbed_query + " " + str(sanitized_sql_result)
    )

    threshold = get_config().privacy.risk_threshold

    privacy_output = {
        "sanitized_query": scrubbed_query,
        "sanitized_context": str(sanitized_sql_result) if sanitized_sql_result else "",
        "redaction_map": redaction_map.to_dict(),
        "risk_score": risk_score,
    }

    if risk_score > threshold:
        logger.error(
            "High PII risk detected (%.2f > %.2f). Blocking cloud access.",
            risk_score,
            threshold,
        )
        return {
            "privacy_output": privacy_output,
            "final_answer": "I'm sorry, but I cannot process this request as it contains sensitive personal information that exceeds our privacy risk threshold.",
        }

    return {
        "privacy_output": privacy_output,
        # We don't set final_answer here as this is an intermediate node
    }
