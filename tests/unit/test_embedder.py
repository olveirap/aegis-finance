"""Unit tests for the local LLM Embedder."""

import pytest
from unittest.mock import AsyncMock

from aegis.kb.embedder import LlamaCppEmbedder
from aegis.kb.pipeline import DocumentChunk
from aegis.kb.ontology import SourceType


@pytest.fixture
def mock_chunks():
    """Returns a list of regular chunks and a structural 'vision' stub chunk."""
    return [
        DocumentChunk(
            chunk_id="doc_0",
            chunk_index=0,
            text="This is valid text to embed.",
            n_tokens=6,
            source_url="http://test.com",
            source_title="Test Document",
            source_type=SourceType.BLOG,
            jurisdiction=["GLOBAL"],
            topic_tags=[],
            relevance_score=0.9,
            language="en",
            entities={}
        ),
        DocumentChunk(
            chunk_id="doc_1",
            chunk_index=1,
            text="   \n   ",  # Structural stub empty chunk
            n_tokens=0,
            source_url="http://test.com",
            source_title="Test Document",
            source_type=SourceType.BLOG,
            jurisdiction=["GLOBAL"],
            topic_tags=[],
            relevance_score=0.0,
            language="en",
            entities={}
        )
    ]


@pytest.mark.asyncio
async def test_embedder_vision_skipping(mock_chunks, monkeypatch):
    embedder = LlamaCppEmbedder(batch_size=1)
    
    # Mock _embed_batch to avoid real HTTP requests
    mock_embed = AsyncMock(return_value=[[0.1, 0.2]])
    monkeypatch.setattr(embedder, "_embed_batch", mock_embed)
    
    results = await embedder.embed(mock_chunks)
    
    assert len(results) == 1
    assert results[0].chunk.chunk_id == "doc_0"
    assert results[0].embedding == [0.1, 0.2]
    
    mock_embed.assert_called_once_with(["This is valid text to embed."])


@pytest.mark.asyncio
async def test_embedder_batching_logic(monkeypatch):
    embedder = LlamaCppEmbedder(batch_size=2)
    
    # Generate 5 mock chunks
    chunks = [
        DocumentChunk(
            chunk_id=f"doc_{i}",
            chunk_index=i,
            text=f"Text {i}",
            n_tokens=2,
            source_url="",
            source_title=None,
            source_type=SourceType.BLOG,
            jurisdiction=[],
            topic_tags=[],
            relevance_score=1.0,
            language="en",
            entities={}
        ) for i in range(5)
    ]
    
    # We expect 3 calls to _embed_batch: [0, 1], [2, 3], [4]
    mock_embed = AsyncMock(side_effect=[
        [[0.0], [0.1]],
        [[0.2], [0.3]],
        [[0.4]]
    ])
    monkeypatch.setattr(embedder, "_embed_batch", mock_embed)
    
    results = await embedder.embed(chunks)
    
    assert len(results) == 5
    assert mock_embed.call_count == 3
    assert results[4].embedding == [0.4]
