# SPDX-License-Identifier: MIT
"""Incremental state tracking for ingestion connectors.

Manages checkpoints in PostgreSQL table `ingestion_state`.
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class IngestionCheckpoint(BaseModel):
    """Represents a state checkpoint for a single source."""

    source_name: str
    last_run_at: datetime | None = None
    last_seen_id: str | None = None
    state_data: dict = Field(default_factory=dict)
    status: str = "idle"


class StateManager:
    """Manages reading and writing source checkpoints.

    In a complete environment, this connects to the Aegis DB `ingestion_state` table.
    """

    def __init__(self, db_pool: object | None = None) -> None:
        self.db_pool = db_pool

    async def get_checkpoint(self, source_name: str) -> IngestionCheckpoint:
        """Fetches the latest checkpoint for the source."""
        # TODO: Implement actual pg query:
        # SELECT last_run_at, last_seen_id, checkpoint, status
        #   FROM ingestion_state WHERE source_name = $1

        # Placeholder for MVP iteration without DB
        return IngestionCheckpoint(source_name=source_name)

    async def save_checkpoint(self, checkpoint: IngestionCheckpoint) -> None:
        """Upserts the checkpoint into the database."""
        # TODO: Implement actual pg UPSERT:
        # INSERT INTO ingestion_state(source_name, last_run_at, last_seen_id, checkpoint, status)
        # VALUES (...) ON CONFLICT (source_name) DO UPDATE SET ...
        pass

    async def mark_source_running(self, source_name: str) -> None:
        checkpoint = await self.get_checkpoint(source_name)
        checkpoint.status = "running"
        await self.save_checkpoint(checkpoint)

    async def mark_source_failed(self, source_name: str) -> None:
        checkpoint = await self.get_checkpoint(source_name)
        checkpoint.status = "failed"
        await self.save_checkpoint(checkpoint)

    async def mark_source_idle(self, source_name: str) -> None:
        checkpoint = await self.get_checkpoint(source_name)
        checkpoint.status = "idle"
        await self.save_checkpoint(checkpoint)
