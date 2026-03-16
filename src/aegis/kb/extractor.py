# SPDX-License-Identifier: MIT
"""Heuristic entity/relation extractor for KB chunks (Task 0.3).

This is a **placeholder** for the DSPy triple extractor introduced in
Milestone 4, Task 4.2.  It combines:
- Regex patterns for Argentine financial identifiers (CUIT, CBU, regulation IDs).
- spaCy ``es_core_news_sm`` NER for named entities (ORG, PER, LOC).

Its output seeds the entity resolver's canonical name registry in Task 4.2.

Setup (one-time):
    Run ``make setup-models`` (or ``python -m spacy download es_core_news_sm``)
    before using this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


# ── Regex patterns ────────────────────────────────────────────────────────────

# CUIT: XX-XXXXXXXX-X
_CUIT_RE = re.compile(r"\b\d{2}-\d{8}-\d\b")

# CBU: 22 consecutive digits
_CBU_RE = re.compile(r"\b\d{22}\b")

# BCRA Communications: "Comunicación A 1234", "Com. A 1234", etc.
_BCRA_COM_RE = re.compile(
    r"Comunicaci[oó]n\s+([A-Z])\s+(\d+)"
    r"|Com(?:unicaci[oó]n)?\.?\s+([A-Z])\s+(\d+)",
    re.IGNORECASE,
)

# CNV Resolutions: "Resolución CNV N° 1234", "Res. CNV Nro 1234", etc.
_CNV_RES_RE = re.compile(
    r"Resoluci[oó]n\s+CNV\s+(?:N[°º]|Nro\.?)\s*(\d+(?:/\d+)?)",
    re.IGNORECASE,
)

# Known Argentine financial regulators (canonical acronyms)
_KNOWN_INSTITUTIONS = frozenset(
    ["BCRA", "CNV", "AFIP", "UIF", "INDEC", "BYMA", "IOL", "MAE"]
)

# Asset name patterns (common Argentine instruments)
_ASSET_RE = re.compile(
    r"\b(CEDEAR[Ss]?|ETF[Ss]?|BOPREAL|Lecap|Lecer|Bono CER"
    r"|Plazo Fijo|FCI|USDT)\b",
    re.IGNORECASE,
)


# ── Output model ──────────────────────────────────────────────────────────────


@dataclass
class ExtractedEntities:
    """Typed entity candidates produced by the heuristic extractor."""

    institutions: list[str] = field(default_factory=list)
    asset_names: list[str] = field(default_factory=list)
    regulation_ids: list[str] = field(default_factory=list)
    raw_entities: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict representation for JSON serialisation."""
        return asdict(self)


# ── Extractor ─────────────────────────────────────────────────────────────────


class HeuristicExtractor:
    """Extracts named entities and regulation IDs from financial text.

    Tries to load ``spacy.load("es_core_news_sm")`` at construction time.
    If the model is unavailable, NER is skipped gracefully and a warning is
    emitted — regex extraction still runs.
    """

    def __init__(self) -> None:
        self._nlp = self._load_spacy()

    @staticmethod
    def _load_spacy():  # type: ignore[return]
        try:
            import spacy  # noqa: PLC0415
            return spacy.load("es_core_news_sm")
        except (ImportError, OSError):
            import warnings  # noqa: PLC0415
            warnings.warn(
                "spaCy model 'es_core_news_sm' not found. "
                "Run 'make setup-models' to enable NER extraction.",
                RuntimeWarning,
                stacklevel=3,
            )
            return None

    # ── public API ────────────────────────────────────────────────────────────

    def extract(self, text: str) -> ExtractedEntities:
        """Extract entities, regulation IDs, and asset names from *text*.

        Args:
            text: Raw chunk text to analyse.

        Returns:
            ``ExtractedEntities`` with typed lists of extracted information.
        """
        if not text.strip():
            return ExtractedEntities()

        regulation_ids: list[str] = []
        institutions: list[str] = []
        asset_names: list[str] = []
        raw_entities: list[dict[str, Any]] = []

        # ── CUIT ──────────────────────────────────────────────────────────────
        for m in _CUIT_RE.finditer(text):
            regulation_ids.append(m.group())

        # ── BCRA Communications ───────────────────────────────────────────────
        for m in _BCRA_COM_RE.finditer(text):
            letter = m.group(1) or m.group(3)
            number = m.group(2) or m.group(4)
            if letter and number:
                regulation_ids.append(f"Comunicación {letter} {number}")

        # ── CNV Resolutions ───────────────────────────────────────────────────
        for m in _CNV_RES_RE.finditer(text):
            regulation_ids.append(f"Resolución CNV N° {m.group(1)}")

        # ── Known institutional acronyms ──────────────────────────────────────
        for acronym in _KNOWN_INSTITUTIONS:
            if re.search(rf"\b{acronym}\b", text):
                institutions.append(acronym)

        # ── Asset names ───────────────────────────────────────────────────────
        seen_assets: set[str] = set()
        for m in _ASSET_RE.finditer(text):
            normalised = m.group().upper()
            if normalised not in seen_assets:
                asset_names.append(m.group())
                seen_assets.add(normalised)

        # ── spaCy NER (fallback-safe) ─────────────────────────────────────────
        if self._nlp is not None:
            doc = self._nlp(text[:100_000])  # spaCy has a hard limit
            for ent in doc.ents:
                raw_entities.append(
                    {"text": ent.text, "label": ent.label_, "start": ent.start_char}
                )
                # Promote ORG entities to institutions if not already there
                if ent.label_ == "ORG" and ent.text not in institutions:
                    institutions.append(ent.text)

        return ExtractedEntities(
            institutions=list(dict.fromkeys(institutions)),  # preserve order, dedupe
            asset_names=asset_names,
            regulation_ids=list(dict.fromkeys(regulation_ids)),
            raw_entities=raw_entities,
        )
