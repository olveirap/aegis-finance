# SPDX-License-Identifier: MIT
"""Residual PII risk scanner using Microsoft Presidio.

Calculates a risk score based on any PII detected in text that survived
previous scrubbing passes.
"""

from __future__ import annotations

import logging
from presidio_analyzer import AnalyzerEngine

logger = logging.getLogger(__name__)


class RiskScorer:
    """Uses Presidio to detect residual PII and calculate a risk score."""

    def __init__(self) -> None:
        try:
            # Initialize with default configuration
            # Note: Presidio needs a spaCy model. If en_core_web_lg is not present,
            # it might fail or use a smaller one.
            self.analyzer = AnalyzerEngine()
        except Exception as e:
            logger.warning(
                "Failed to initialize Presidio Analyzer: %s. Risk scoring will be disabled.",
                e,
            )
            self.analyzer = None

    def calculate_risk(self, text: str) -> float:
        """Analyze text and return a risk score between 0.0 and 1.0.

        Args:
            text: Scrubbed text to analyze.

        Returns:
            Risk score. 0.0 means no PII detected.
        """
        if not self.analyzer or not text.strip():
            return 0.0

        try:
            # We look for common PII entities
            results = self.analyzer.analyze(
                text=text,
                language="en",  # Presidio works best with 'en', but can be configured for 'es'
                entities=[
                    "PERSON",
                    "EMAIL_ADDRESS",
                    "PHONE_NUMBER",
                    "LOCATION",
                    "DATE_TIME",
                    "CRYPTO",
                    "IBAN_CODE",
                ],
            )

            if not results:
                return 0.0

            # Calculate score as the maximum confidence of any detected entity
            # adjusted by the density of detections.
            max_score = max(r.score for r in results)

            # If we see multiple high-confidence detections, boost the risk
            if len(results) > 3 and max_score > 0.5:
                return min(1.0, max_score * 1.2)

            return float(max_score)

        except Exception as e:
            logger.error("Error during risk analysis: %s", e)
            return 1.0  # Fail-safe: high risk on error
