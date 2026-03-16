# SPDX-License-Identifier: MIT
"""Metadata schema for knowledge-base chunks.

Every chunk stored in ``kb_chunks`` carries a :class:`ChunkMetadata` sidecar
that drives filtering, provenance tracking, and taxonomy-aware retrieval.

Jurisdiction is an *orthogonal facet* — it is not a topic category.
Values are ISO 3166-1 alpha-2 codes (``"AR"``, ``"US"``) or ``"GLOBAL"``
for content that is not country-specific.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from aegis.kb.ontology import SourceType, SubTopic
from aegis.kb.temporal import TemporalInterval

# Allowed jurisdiction codes.  GLOBAL is a sentinel, not a real ISO code.
_VALID_JURISDICTIONS = frozenset(
    {
        "GLOBAL",
        # Latin America
        "AR",
        "BR",
        "CL",
        "CO",
        "MX",
        "UY",
        "PE",
        # North America / Europe (most common foreign references)
        "US",
        "GB",
        "DE",
        "ES",
    }
)


class ChunkMetadata(BaseModel):
    """Pydantic v2 model describing one knowledge-base chunk."""

    # ── Source provenance ─────────────────────────────────────────────────
    source_url: str = Field(
        ..., description="Origin URL, book title, or file path."
    )
    source_type: SourceType = Field(
        ..., description="How the content was acquired."
    )
    date_published: date | None = Field(
        default=None, description="Publication date of the source document."
    )
    date_ingested: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the chunk was ingested.",
    )

    # ── Taxonomy facets ──────────────────────────────────────────────────
    topic_tags: list[SubTopic] = Field(
        min_length=1,
        description="One or more ontology subtopics.",
    )
    jurisdiction: list[str] = Field(
        default=["GLOBAL"],
        min_length=1,
        description=(
            "ISO 3166-1 alpha-2 codes or 'GLOBAL'. "
            "Indicates which countries/regions the content applies to."
        ),
    )

    # ── Quality & linking ────────────────────────────────────────────────
    language: str = Field(
        default="es-AR",
        description="BCP 47 language tag (e.g., 'es-AR', 'en-US', 'en').",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Relevance score (0–1) against the topic taxonomy.",
    )
    entity_ids: list[UUID] = Field(
        default_factory=list,
        description="Links to kb_entities rows for graph prep.",
    )

    # ── Temporal model ───────────────────────────────────────────────────
    temporal_validity: TemporalInterval | None = Field(
        default=None,
        description="Time interval during which the chunk is valid.",
    )
    superseded_by: str | None = Field(
        default=None,
        description="ID of the chunk/regulation that supersedes this one.",
    )
    causal_chain: list[str] = Field(
        default_factory=list,
        description="List of IDs forming the causal chain (e.g., amends X, amends Y).",
    )

    # ── Validators ───────────────────────────────────────────────────────

    @field_validator("jurisdiction", mode="before")
    @classmethod
    def _normalise_jurisdiction(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for code in v:
            upper = code.strip().upper()
            if upper not in _VALID_JURISDICTIONS:
                raise ValueError(
                    f"Unknown jurisdiction code '{code}'. "
                    f"Allowed: {sorted(_VALID_JURISDICTIONS)}"
                )
            out.append(upper)
        return out
