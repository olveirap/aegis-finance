# SPDX-License-Identifier: MIT
"""Unit tests for the Tagger (Task 0.3)."""

from __future__ import annotations

import pytest

from aegis.kb.tagger import BaseTagger, HeuristicTagger, LLMTagger
from aegis.kb.ontology import SubTopic


# ── BaseTagger interface ──────────────────────────────────────────────────────


def test_base_tagger_is_abstract() -> None:
    """BaseTagger cannot be instantiated directly."""
    import inspect

    assert inspect.isabstract(BaseTagger)


def test_llm_tagger_raises_not_implemented() -> None:
    """LLMTagger stub enforces the interface contract but is not wired yet."""
    t = LLMTagger()
    with pytest.raises(NotImplementedError):
        t.tag("some financial text")


# ── HeuristicTagger ───────────────────────────────────────────────────────────


def test_cedear_text_returns_cedears_tag() -> None:
    t = HeuristicTagger()
    tags = t.tag("Los CEDEARs de Apple cotizan en pesos y dólares en el mercado local.")
    assert SubTopic.CEDEARS in tags


def test_inflation_text_returns_inflation_tag() -> None:
    t = HeuristicTagger()
    tags = t.tag("La inflación interanual alcanzó el 140 % según el IPC del INDEC.")
    assert SubTopic.INFLATION in tags


def test_cpi_english_maps_to_inflation() -> None:
    t = HeuristicTagger()
    tags = t.tag("The CPI rose by 3.2% in January according to BLS data.")
    assert SubTopic.INFLATION in tags


def test_mixed_topic_text_returns_multiple_tags() -> None:
    t = HeuristicTagger()
    text = (
        "Bienes personales y ganancias afectan la rentabilidad de los CEDEARs. "
        "El BCRA regula el acceso al MEP."
    )
    tags = t.tag(text)
    # Should detect at least CEDEARS + WEALTH_TAX or INCOME_TAX + REGULATORY_BODIES
    assert len(tags) >= 2


def test_unknown_text_returns_empty_list() -> None:
    t = HeuristicTagger()
    tags = t.tag("The quick brown fox jumps over the lazy dog.")
    assert tags == []


def test_tags_are_subtopic_instances() -> None:
    t = HeuristicTagger()
    tags = t.tag("presupuesto familiar y ahorro de emergencia")
    for tag in tags:
        assert isinstance(tag, SubTopic)


def test_regulatory_bodies_keyword() -> None:
    t = HeuristicTagger()
    tags = t.tag("La CNV emitió una resolución restringiendo la operatoria del MEP.")
    assert SubTopic.REGULATORY_BODIES in tags


def test_etfs_keyword() -> None:
    t = HeuristicTagger()
    tags = t.tag("Investing in ETFs provides broad market exposure.")
    assert SubTopic.ETFS in tags


def test_budgeting_spanish_keyword() -> None:
    t = HeuristicTagger()
    tags = t.tag(
        "Mantener un presupuesto mensual es clave para las finanzas personales."
    )
    assert SubTopic.BUDGETING in tags


def test_no_duplicate_tags() -> None:
    t = HeuristicTagger()
    text = "cedear cedears CEDEAR CEDEARs"
    tags = t.tag(text)
    assert len(tags) == len(set(tags)), "Tags must not contain duplicates"
