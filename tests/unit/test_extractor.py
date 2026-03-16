# SPDX-License-Identifier: MIT
"""Unit tests for the HeuristicExtractor (Task 0.3)."""

from __future__ import annotations

import pytest

from aegis.kb.extractor import ExtractedEntities, HeuristicExtractor


# ── fixture text ─────────────────────────────────────────────────────────────


BCRA_TEXT = (
    "El Banco Central de la República Argentina (BCRA) emitió la Comunicación A 7654 "
    "estableciendo nuevas restricciones cambiarias. La CNV también publicó la "
    "Resolución CNV N° 990/2024 sobre fondos comunes de inversión."
)

CUIT_TEXT = (
    "El contribuyente con CUIT 20-12345678-9 presentó la declaración ante la AFIP."
)

EMPTY_TEXT = ""


# ── HeuristicExtractor construction ──────────────────────────────────────────


def test_extractor_constructs() -> None:
    e = HeuristicExtractor()
    assert e is not None


# ── ExtractedEntities structure ───────────────────────────────────────────────


def test_extracted_entities_empty_text() -> None:
    e = HeuristicExtractor()
    result = e.extract(EMPTY_TEXT)
    assert isinstance(result, ExtractedEntities)
    assert result.institutions == []
    assert result.regulation_ids == []
    assert result.asset_names == []


# ── Regulation IDs ────────────────────────────────────────────────────────────


def test_bcra_communication_found() -> None:
    e = HeuristicExtractor()
    result = e.extract(BCRA_TEXT)
    assert any("A 7654" in r or "7654" in r for r in result.regulation_ids), (
        f"Expected BCRA communication in regulation_ids, got: {result.regulation_ids}"
    )


def test_cnv_resolution_found() -> None:
    e = HeuristicExtractor()
    result = e.extract(BCRA_TEXT)
    assert any("990" in r for r in result.regulation_ids), (
        f"Expected CNV resolution in regulation_ids, got: {result.regulation_ids}"
    )


# ── CUIT ─────────────────────────────────────────────────────────────────────


def test_cuit_found_in_text() -> None:
    e = HeuristicExtractor()
    result = e.extract(CUIT_TEXT)
    # CUIT should appear in regulation_ids or a dedicated field
    all_extracted = " ".join(result.regulation_ids + result.institutions)
    assert "20-12345678-9" in all_extracted or any(
        "20-12345678-9" in str(ent.get("text", "")) for ent in result.raw_entities
    ), f"CUIT not found in extraction output: {result}"


# ── Institutions ──────────────────────────────────────────────────────────────


def test_known_institution_extracted() -> None:
    e = HeuristicExtractor()
    result = e.extract(BCRA_TEXT)
    # BCRA or CNV should appear in institutions (or raw_entities from spaCy)
    all_orgs = " ".join(result.institutions)
    raw_orgs = " ".join(str(ent.get("text", "")) for ent in result.raw_entities)
    assert "BCRA" in all_orgs or "BCRA" in raw_orgs or "Central" in raw_orgs, (
        f"BCRA not found in institutions={result.institutions}, raw={result.raw_entities}"
    )


def test_afip_extracted() -> None:
    e = HeuristicExtractor()
    result = e.extract(CUIT_TEXT)
    all_text = " ".join(result.institutions) + " ".join(
        str(ent.get("text", "")) for ent in result.raw_entities
    )
    assert "AFIP" in all_text, f"AFIP not found: institutions={result.institutions}"


# ── ExtractedEntities as dict ─────────────────────────────────────────────────


def test_extracted_entities_to_dict() -> None:
    e = HeuristicExtractor()
    result = e.extract(BCRA_TEXT)
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "institutions" in d
    assert "regulation_ids" in d
    assert "asset_names" in d
    assert "raw_entities" in d
