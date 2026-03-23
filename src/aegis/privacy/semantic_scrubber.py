# SPDX-License-Identifier: MIT
"""Semantic PII scrubber using local LLM audit.

Uses Qwen 3.5 via llama.cpp to identify contextual PII (names, addresses,
specific financial details) that regex might miss.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx

from aegis.config import get_config

if TYPE_CHECKING:
    from aegis.privacy.redaction_map import RedactionMap

logger = logging.getLogger(__name__)

SEMANTIC_SYSTEM_PROMPT = """You are a privacy auditor. Your goal is to identify all personally identifiable information (PII) or sensitive financial details in the user's text.

Identify:
- People's full names
- Physical addresses
- Specific financial entities or assets not already bucketed
- Any other information that could identify the user

Output ONLY a JSON list of strings found in the text that should be redacted.
If nothing is found, return an empty list [].

Example:
Text: "My name is Juan Perez and I live in Av. Santa Fe 1234."
Output: ["Juan Perez", "Av. Santa Fe 1234"]

Text: {text}
"""


class SemanticScrubber:
    """Pass 2 scrubber using LLM semantic audit."""

    async def scrub(self, text: str, redaction_map: RedactionMap) -> str:
        """Audit text with LLM and redact found entities.

        Args:
            text: Input text (likely already regex-scrubbed).
            redaction_map: Map to store redactions.

        Returns:
            Further scrubbed text.
        """
        config = get_config()
        url = config.llm.local.llama_cpp_server

        # Skip if no local LLM configured or reachable
        if not url:
            return text

        messages = [
            {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT.format(text=text)},
            {"role": "user", "content": "Identify entities to redact."},
        ]

        try:
            response = await self._call_llm(messages, url)
            entities = self._parse_response(response)

            result = text
            for entity in entities:
                # Avoid redacting already bucketed or tokenized items
                if entity.startswith("[") and entity.endswith("]"):
                    continue

                token = redaction_map.get_token(entity, "ENTITY")
                result = result.replace(entity, token)

            return result

        except Exception as e:
            logger.warning(
                "Semantic scrubbing failed: %s. Proceeding with Pass 1 results.", e
            )
            return text

    async def _call_llm(self, messages: list[dict[str, str]], url: str) -> str:
        """Internal helper to call llama.cpp."""
        endpoint = f"{url}/v1/chat/completions"
        payload = {
            "model": "qwen3.5",
            "messages": messages,
            "temperature": 0.0,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, text: str) -> list[str]:
        """Extract the JSON list from LLM output."""
        try:
            # Simple cleanup for markdown
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            start_idx = cleaned.find("[")
            end_idx = cleaned.rfind("]") + 1
            if start_idx >= 0 and end_idx > start_idx:
                cleaned = cleaned[start_idx:end_idx]

            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
