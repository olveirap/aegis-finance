# SPDX-License-Identifier: MIT
"""Regex-based PII scrubber for Argentine and financial patterns.

Identifies and redacts common identifiers (CUIT, CBU, Email) and buckets
financial amounts to prevent leakage of exact values.
"""

from __future__ import annotations

import re
import bisect
from typing import TYPE_CHECKING

from aegis.config import get_config

if TYPE_CHECKING:
    from aegis.privacy.redaction_map import RedactionMap

# ---------------------------------------------------------------------------
# Regex Patterns
# ---------------------------------------------------------------------------

# Argentine Tax ID (CUIT/CUIL): 20-12345678-9 or 20123456789
CUIT_RE = re.compile(r"\b\d{2}-?\d{8}-?\d\b")

# Argentine Bank Account (CBU/CVU): 22 digits
CBU_RE = re.compile(r"\b\d{22}\b")

# Standard Email
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# Financial Amounts (ARS/USD/EUR followed by numbers or vice versa)
# Matches: $1.234,56 or 1.234,56 ARS or USD 500
AMOUNT_RE = re.compile(
    r"(?P<currency>ARS|USD|USDT|EUR|\$|U\$S)\s*(?P<amount>\d+(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)\b",
    re.IGNORECASE,
)


class RegexScrubber:
    """Pass 1 scrubber using regular expressions for pattern matching."""

    def scrub(self, text: str, redaction_map: RedactionMap) -> str:
        """Apply all regex patterns to the text.

        Args:
            text: Input text to scrub.
            redaction_map: Map to store redactions.

        Returns:
            Scrubbed text with tokens and buckets.
        """
        result = text

        # 1. Scrub CUIT
        for match in CUIT_RE.findall(result):
            token = redaction_map.get_token(match, "CUIT")
            result = result.replace(match, token)

        # 2. Scrub CBU
        for match in CBU_RE.findall(result):
            token = redaction_map.get_token(match, "CBU")
            result = result.replace(match, token)

        # 3. Scrub Emails
        for match in EMAIL_RE.findall(result):
            token = redaction_map.get_token(match, "EMAIL")
            result = result.replace(match, token)

        # 4. Bucket Amounts
        result = self._apply_bucketing(result)

        return result

    def _apply_bucketing(self, text: str) -> str:
        """Replace exact amounts with range buckets."""
        config = get_config().privacy.redaction_buckets

        def _replacer(match: re.Match) -> str:
            curr_symbol = match.group("currency").upper()
            raw_amount = match.group("amount")

            # Normalize amount string to float
            # Replace thousands dot, then decimal comma with dot
            clean_amt = raw_amount.replace(".", "").replace(",", ".")
            try:
                val = float(clean_amt)
            except ValueError:
                return match.group(0)  # Give up on this one

            # Determine currency type
            is_usd = curr_symbol in {"USD", "USDT", "U$S"}
            buckets = config.usd if is_usd else config.ars
            curr_label = "USD" if is_usd else "ARS"

            # Find bucket
            idx = bisect.bisect_right(buckets, val)
            if idx == 0:
                bucket_str = f"<{buckets[0]}"
            elif idx >= len(buckets):
                bucket_str = f">{buckets[-1]}"
            else:
                low = buckets[idx - 1]
                high = buckets[idx]
                # Format for readability
                low_k = f"{low // 1000}k" if low >= 1000 else str(low)
                high_k = f"{high // 1000}k" if high >= 1000 else str(high)
                bucket_str = f"{low_k}_{high_k}"

            return f"[{curr_label}_{bucket_str}]"

        return AMOUNT_RE.sub(_replacer, text)
