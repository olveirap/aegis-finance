# SPDX-License-Identifier: MIT
"""Ontology tagger for KB chunks.

Ships two implementations:
- ``HeuristicTagger`` — keyword-based, available immediately (this task).
- ``LLMTagger``       — interface stub; wired to Qwen 3.5 via llama.cpp in Task 0.4.

Both implement ``BaseTagger`` so callers can swap implementations without
changing call sites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from aegis.kb.ontology import SubTopic


# ── Keyword map ───────────────────────────────────────────────────────────────
# Maps each SubTopic to a list of lowercase keywords/phrases. Matching is
# case-insensitive substring search over the input text.
_KEYWORD_MAP: dict[SubTopic, list[str]] = {
    # Personal Finance
    SubTopic.BUDGETING: ["presupuesto", "budget", "gastos", "expenses", "household"],
    SubTopic.SAVING: ["ahorro", "saving", "savings", "reserva"],
    SubTopic.EMERGENCY_FUND: ["fondo de emergencia", "emergency fund", "colchón"],
    SubTopic.DEBT_MANAGEMENT: [
        "deuda",
        "debt",
        "crédito personal",
        "refinanciación",
        "préstamo",
    ],
    SubTopic.INSURANCE: ["seguro", "insurance", "cobertura", "póliza"],
    # Investing
    SubTopic.STOCKS: ["acción", "acciones", "stock", "stocks", "equity", "bolsa"],
    SubTopic.BONDS: ["bono", "bonos", "bond", "bonds", "renta fija", "fixed income"],
    SubTopic.CEDEARS: ["cedear", "cedears"],
    SubTopic.FCIS: [
        "fondo común",
        "fondo de inversión",
        "fci",
        "fondos comunes",
        "mutual fund",
    ],
    SubTopic.ETFS: ["etf", "etfs", "exchange traded fund"],
    SubTopic.CRYPTO: ["crypto", "bitcoin", "ethereum", "criptomoneda", "criptoactivo"],
    SubTopic.MUTUAL_FUNDS: [
        "fondo mutuo",
        "mutual fund",
        "fondo de inversión colectiva",
    ],
    # Tax & Regulation
    SubTopic.INCOME_TAX: ["ganancias", "income tax", "impuesto a las ganancias"],
    SubTopic.WEALTH_TAX: ["bienes personales", "wealth tax", "patrimonio"],
    SubTopic.CURRENCY_CONTROLS: [
        "cepo",
        "mep",
        "ccl",
        "dólar blue",
        "controles cambiarios",
        "currency control",
        "tipo de cambio",
        "cotización",
    ],
    SubTopic.INFLATION: [
        "inflación",
        "inflation",
        "ipc",
        "cpi",
        "indec",
        "precio",
        "precios",
    ],
    SubTopic.REGULATORY_BODIES: [
        "bcra",
        "cnv",
        "afip",
        "uif",
        "comisión nacional de valores",
        "banco central",
        "regulador",
    ],
    SubTopic.TAX_PLANNING: [
        "planificación fiscal",
        "tax planning",
        "evasión",
        "elusión",
        "declaración",
    ],
    # Real Estate
    SubTopic.MORTGAGE: ["hipoteca", "mortgage", "crédito hipotecario"],
    SubTopic.RENTAL: ["alquiler", "rental", "inquilino", "arrendamiento"],
    SubTopic.PROPERTY_TAX: [
        "abl",
        "inmobiliario",
        "property tax",
        "impuesto inmobiliario",
    ],
}


# ── Abstract base ─────────────────────────────────────────────────────────────


class BaseTagger(ABC):
    """Interface contract for all ontology taggers."""

    @abstractmethod
    def tag(self, text: str) -> list[SubTopic]:
        """Return a deduplicated list of ``SubTopic`` values matching *text*.

        Args:
            text: The chunk text to classify.

        Returns:
            Matched sub-topics, sorted by relevance score descending.
            Returns an empty list when no topics match.
        """


# ── Heuristic implementation ──────────────────────────────────────────────────


class HeuristicTagger(BaseTagger):
    """Keyword-based ontology tagger.

    Scores each ``SubTopic`` by counting keyword hits in the lowercased input.
    Returns sub-topics with at least one hit, sorted by hit count descending.
    """

    def tag(self, text: str) -> list[SubTopic]:  # noqa: D102
        lowered = text.lower()
        scores: dict[SubTopic, int] = {}
        for subtopic, keywords in _KEYWORD_MAP.items():
            hits = sum(kw in lowered for kw in keywords)
            if hits:
                scores[subtopic] = hits
        return sorted(scores, key=scores.__getitem__, reverse=True)


# ── LLM stub ─────────────────────────────────────────────────────────────────


class LLMTagger(BaseTagger):
    """Qwen 3.5 tagger via llama.cpp — wired in Task 0.4.

    This stub enforces the ``BaseTagger`` interface so downstream code can
    reference ``LLMTagger`` today without a running llama.cpp sidecar.
    """

    def tag(self, text: str) -> list[SubTopic]:  # noqa: D102
        raise NotImplementedError(
            "LLMTagger requires a running llama.cpp sidecar. Wire in Task 0.4."
        )
