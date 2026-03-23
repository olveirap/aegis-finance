# SPDX-License-Identifier: MIT
"""Temporal modeling for SAT-Graph RAG.

Provides structures for representing time intervals, temporal validity of chunks,
and causal relationships (e.g. regulations superseding each other).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TemporalInterval(BaseModel):
    """An interval during which a piece of knowledge is considered valid."""

    t_start: datetime | None = Field(
        default=None, description="Start of validity period."
    )
    t_end: datetime | None = Field(
        default=None, description="End of validity period (if known)."
    )

    @model_validator(mode="after")
    def validate_interval(self) -> TemporalInterval:
        if self.t_start and self.t_end and self.t_start > self.t_end:
            raise ValueError("t_start cannot be after t_end")
        return self


class CausalActionNode(BaseModel):
    """Reified action node for tracking legislative or market events over time.

    In a property graph, instead of just A -> AMENDS -> B, we can have:
    A -> ORIGINATES -> ActionNode(Amends) -> TARGETS -> B
    """

    action_type: str = Field(
        ..., description="Type of action (e.g., 'AMEND', 'SUPERSEDE')."
    )
    effective_date: datetime = Field(..., description="When the action takes effect.")
    description: str = Field(
        default="", description="Description of the causal action."
    )


def point_in_time_filter(t: datetime | None = None) -> dict[str, Any]:
    """Generates a query filter for valid chunks at a given point in time.

    Args:
        t: The target datetime. Defaults to current UTC time.

    Returns:
        A dictionary filter (e.g., for Vector store or graph DB metadata filtering)
        representing the temporal constraint: t_start <= t AND (t_end IS NULL OR t_end > t).
    """
    if t is None:
        t = datetime.now(timezone.utc)

    # Example MongoDB/pgvector JSONB style filter:
    return {
        "$and": [
            {
                "$or": [
                    {"temporal_validity.t_start": {"$lte": t.isoformat()}},
                    {"temporal_validity.t_start": None},
                ]
            },
            {
                "$or": [
                    {"temporal_validity.t_end": {"$gt": t.isoformat()}},
                    {"temporal_validity.t_end": None},
                ]
            },
        ]
    }
