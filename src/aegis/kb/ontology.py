# SPDX-License-Identifier: MIT
"""Topic taxonomy, graph entity/edge types, and controlled vocabulary.

Design decisions
~~~~~~~~~~~~~~~~
* **Faceted classification** – three orthogonal facets:
    Topic  (what the content is about),
    Jurisdiction (where it applies),
    SourceType   (how it was acquired).
* "Argentine-specific" is *not* a topic category.  Jurisdiction is metadata
  attached to any topic via ``jurisdiction: list[str]`` (ISO 3166-1 α-2).
* Graph node/edge types prepare for a future Graph DB without coupling to one.
* Aligns where possible with FIBO (Financial Industry Business Ontology).
"""

from __future__ import annotations

from enum import StrEnum, unique


# ── Topic facet ──────────────────────────────────────────────────────────────


@unique
class TopicCategory(StrEnum):
    """Top-level knowledge domains (mutually exclusive per chunk)."""

    PERSONAL_FINANCE = "personal_finance"
    INVESTING = "investing"
    TAX_AND_REGULATION = "tax_and_regulation"
    REAL_ESTATE = "real_estate"


@unique
class SubTopic(StrEnum):
    """Leaf-level topics. Each belongs to exactly one TopicCategory."""

    # ── Personal Finance ─────────────────────────────────────────────────
    BUDGETING = "budgeting"
    SAVING = "saving"
    EMERGENCY_FUND = "emergency_fund"
    DEBT_MANAGEMENT = "debt_management"
    INSURANCE = "insurance"

    # ── Investing ────────────────────────────────────────────────────────
    STOCKS = "stocks"
    BONDS = "bonds"
    CEDEARS = "cedears"
    FCIS = "fcis"
    ETFS = "etfs"
    CRYPTO = "crypto"
    MUTUAL_FUNDS = "mutual_funds"

    # ── Tax & Regulation ─────────────────────────────────────────────────
    INCOME_TAX = "income_tax"
    WEALTH_TAX = "wealth_tax"
    CURRENCY_CONTROLS = "currency_controls"
    INFLATION = "inflation"
    REGULATORY_BODIES = "regulatory_bodies"
    TAX_PLANNING = "tax_planning"

    # ── Real Estate ──────────────────────────────────────────────────────
    MORTGAGE = "mortgage"
    RENTAL = "rental"
    PROPERTY_TAX = "property_tax"


# Canonical parent mapping — keeps hierarchy navigable without a tree class.
SUBTOPIC_PARENTS: dict[SubTopic, TopicCategory] = {
    # Personal Finance
    SubTopic.BUDGETING: TopicCategory.PERSONAL_FINANCE,
    SubTopic.SAVING: TopicCategory.PERSONAL_FINANCE,
    SubTopic.EMERGENCY_FUND: TopicCategory.PERSONAL_FINANCE,
    SubTopic.DEBT_MANAGEMENT: TopicCategory.PERSONAL_FINANCE,
    SubTopic.INSURANCE: TopicCategory.PERSONAL_FINANCE,
    # Investing
    SubTopic.STOCKS: TopicCategory.INVESTING,
    SubTopic.BONDS: TopicCategory.INVESTING,
    SubTopic.CEDEARS: TopicCategory.INVESTING,
    SubTopic.FCIS: TopicCategory.INVESTING,
    SubTopic.ETFS: TopicCategory.INVESTING,
    SubTopic.CRYPTO: TopicCategory.INVESTING,
    SubTopic.MUTUAL_FUNDS: TopicCategory.INVESTING,
    # Tax & Regulation
    SubTopic.INCOME_TAX: TopicCategory.TAX_AND_REGULATION,
    SubTopic.WEALTH_TAX: TopicCategory.TAX_AND_REGULATION,
    SubTopic.CURRENCY_CONTROLS: TopicCategory.TAX_AND_REGULATION,
    SubTopic.INFLATION: TopicCategory.TAX_AND_REGULATION,
    SubTopic.REGULATORY_BODIES: TopicCategory.TAX_AND_REGULATION,
    SubTopic.TAX_PLANNING: TopicCategory.TAX_AND_REGULATION,
    # Real Estate
    SubTopic.MORTGAGE: TopicCategory.REAL_ESTATE,
    SubTopic.RENTAL: TopicCategory.REAL_ESTATE,
    SubTopic.PROPERTY_TAX: TopicCategory.REAL_ESTATE,
}

# Ensure completeness at import time.
assert set(SUBTOPIC_PARENTS.keys()) == set(SubTopic), (
    "SUBTOPIC_PARENTS must map every SubTopic member"
)


def children_of(category: TopicCategory) -> list[SubTopic]:
    """Return all SubTopics that belong to *category*."""
    return [st for st, parent in SUBTOPIC_PARENTS.items() if parent == category]


# ── Source-type facet ────────────────────────────────────────────────────────


@unique
class SourceType(StrEnum):
    """How the content was originally acquired."""

    BLOG = "blog"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    REGULATION = "regulation"
    BOOK_SUMMARY = "book_summary"
    USER_NOTE = "user_note"


# ── Graph-prep types ─────────────────────────────────────────────────────────


@unique
class GraphNodeType(StrEnum):
    """Entity types for the future knowledge graph."""

    CONCEPT = "concept"
    REGULATION = "regulation"
    ASSET = "asset"
    INSTITUTION = "institution"
    TAX_RULE = "tax_rule"


@unique
class GraphEdgeType(StrEnum):
    """Relationship types for the future knowledge graph."""

    RELATES_TO = "relates_to"
    REGULATES = "regulates"
    DEPENDS_ON = "depends_on"
    TAXED_BY = "taxed_by"
    ISSUED_BY = "issued_by"
