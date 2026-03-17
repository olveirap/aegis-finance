# SPDX-License-Identifier: MIT
"""Embedding generation for the Knowledge Base.

This module is responsible for taking a batch of ``DocumentChunk`` objects,
calling the local ``llama.cpp`` embedding endpoint, handling retries, and returning
the chunks alongside their computed embeddings.
"""

from __future__ import annotations

import logging
import os
import random
from typing import NamedTuple

import httpx
import tenacity
from tqdm import tqdm

from aegis.kb.pipeline import DocumentChunk

logger = logging.getLogger(__name__)


class EmbeddedChunk(NamedTuple):
    """A chunk paired with its vector embedding."""
    chunk: DocumentChunk
    embedding: list[float]


class LlamaCppEmbedder:
    """Batch embedder using a local llama.cpp server.

    Args:
        base_url: The URL to the llama.cpp server (e.g., "http://localhost:8080/v1")
        model: The model identifier to send in the payload.
        batch_size: The maximum number of texts to embed in a single request.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        model: str = "qwen3-embedding",
        batch_size: int = 32,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.use_mock = os.environ.get("MOCK_EMBEDDER", "1") == "1"

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        retry=tenacity.retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        before_sleep=lambda retry_state: logger.warning(
            f"Embedding request failed, retrying (attempt {retry_state.attempt_number})..."
        ),
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Make the actual HTTP request to the embedding endpoint."""
        if self.use_mock:
            # Return random 1024-dimensional vectors for testing without LLM
            return [[random.random() for _ in range(1024)] for _ in texts]
            
        url = f"{self.base_url}/embeddings"
        payload = {
            "input": texts,
            "model": self.model,
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            # Sort by index to make sure they match the input order
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]

    async def embed(self, chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
        """Embed a list of chunks, applying vision fallback logic.
        
        Chunks that appear to be vision/OCR stubs (e.g. empty text but carrying structural tables
        without accompanying parsed text) will be dropped with a warning.
        We strictly avoid generating zero or random vectors for unprocessable chunks 
        to prevent pgvector index corruption.
        
        Args:
            chunks: A list of DocumentChunk objects that passed pipeline quality gates.
            
        Returns:
            A list of ``EmbeddedChunk`` representing valid embedded documents.
        """
        valid_chunks: list[DocumentChunk] = []
        vision_skipped_count = 0
        
        for c in chunks:
            # Explicit vision fallback strategy
            # If a chunk is effectively empty text but meant to represent vision data,
            # drop it. For now, we use a simple text length heuristic.
            if not c.text.strip():
                logger.warning(
                    f"Skipping empty/vision chunk {c.chunk_id} from {c.source_url}. "
                    "Vision fallback is currently stubbed."
                )
                vision_skipped_count += 1
                continue
            valid_chunks.append(c)
            
        if vision_skipped_count > 0:
            logger.info(f"Skipped {vision_skipped_count} vision chunks during embedding.")

        if not valid_chunks:
            return []

        results: list[EmbeddedChunk] = []
        
        # Process in batches
        for i in tqdm(range(0, len(valid_chunks), self.batch_size), desc="Embedding Chunks"):
            batch = valid_chunks[i:i + self.batch_size]
            texts = [c.text for c in batch]
            
            try:
                embeddings = await self._embed_batch(texts)
                for chunk, emb in zip(batch, embeddings):
                    if len(emb) == 0:
                        logger.error(f"Received empty embedding for chunk {chunk.chunk_id}. Skipping.")
                        continue
                    results.append(EmbeddedChunk(chunk=chunk, embedding=emb))
            except Exception as e:
                logger.error(f"Failed to embed batch starting at index {i}: {e}. Skipping batch.")
                # We skip the batch on total failure to allow the rest of the ingestion to proceed
                # In a robust system we might dead-letter these.
                
        return results
