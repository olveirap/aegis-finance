# SPDX-License-Identifier: MIT
"""In-memory mapping between original values and redaction tokens.

Provides a bidirectional map to redact sensitive information and reconstruct
it later if needed.
"""

from __future__ import annotations

import re


class RedactionMap:
    """Manages the mapping between sensitive data and anonymized tokens.

    Tokens are generated in the format [CATEGORY_INDEX], e.g., [PERSON_1].
    """

    def __init__(self) -> None:
        self._to_token: dict[str, str] = {}
        self._to_original: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def get_token(self, original_value: str, category: str) -> str:
        """Get or create a redaction token for a given value and category.

        Args:
            original_value: The sensitive string to redact.
            category: The type of entity (e.g., PERSON, EMAIL, CUIT).

        Returns:
            A token string like [CATEGORY_N].
        """
        key = f"{category}:{original_value}"
        if key in self._to_token:
            return self._to_token[key]

        # Generate new token
        count = self._counters.get(category, 0) + 1
        self._counters[category] = count
        token = f"[{category}_{count}]"

        self._to_token[key] = token
        self._to_original[token] = original_value
        return token

    def reconstruct(self, text: str) -> str:
        """Replace all tokens in the text with their original values.

        Args:
            text: The anonymized text containing tokens.

        Returns:
            The original text with sensitive info restored.
        """
        # Find all tokens like [CATEGORY_N]
        tokens = re.findall(r"\[[A-Z_]+_\d+\]", text)
        result = text
        for token in set(tokens):
            if token in self._to_original:
                result = result.replace(token, self._to_original[token])
        return result

    def to_dict(self) -> dict[str, str]:
        """Return the mapping as a dictionary."""
        return self._to_original.copy()

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> RedactionMap:
        """Create a RedactionMap from a dictionary."""
        instance = cls()
        instance._to_original = data.copy()
        # Reconstruct the reverse map and counters
        for token, original in data.items():
            match = re.match(r"\[([A-Z_]+)_(\d+)\]", token)
            if match:
                category, index = match.groups()
                instance._to_token[f"{category}:{original}"] = token
                idx_val = int(index)
                instance._counters[category] = max(
                    instance._counters.get(category, 0), idx_val
                )
        return instance
