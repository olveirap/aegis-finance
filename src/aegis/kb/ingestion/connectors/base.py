# SPDX-License-Identifier: MIT
"""Base abstraction for ingestion connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from aegis.kb.ingestion.models import SourceMeta
from aegis.kb.ingestion.registry import SourceConfig


class BaseConnector(ABC):
    """Abstract base class for all ingestion connectors.
    
    Connectors are responsible for transport (how to get the data) and emit raw
    bytes along with initial source metadata.
    """

    @abstractmethod
    async def fetch(
        self, config: SourceConfig, checkpoint: dict | None = None
    ) -> AsyncIterator[tuple[bytes, SourceMeta]]:
        """Yields raw bytes and metadata from the source.
        
        Args:
            config: Configuration for the source (e.g., base_url, auth).
            checkpoint: Optional state dictionary for resume-on-crash behavior.
            
        Yields:
            Tuples containing the raw bytes and the initial SourceMeta.
        """
        # This is an abstract async generator method; implementations must yield
        # (bytes, SourceMeta) tuples. Subclasses must override this method.
        if False:
            yield NotImplemented
        raise NotImplementedError("BaseConnector.fetch must be implemented by subclasses.")
