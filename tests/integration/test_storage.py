"""Tests for PostgreSQL Vector Storage backend."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from aegis.kb.storage import PgVectorStore
from aegis.kb.embedder import EmbeddedChunk
from aegis.kb.pipeline import DocumentChunk
from aegis.kb.ontology import SourceType

@pytest.fixture
def mock_embedded_chunks():
    return [
        EmbeddedChunk(
            chunk=DocumentChunk(
                chunk_id="test_doc_0",
                chunk_index=0,
                text="Test text content",
                n_tokens=4,
                source_url="http://test.com",
                source_title="Test Title",
                source_type=SourceType.BLOG,
                jurisdiction=["ARGENTINA"],
                topic_tags=[],
                relevance_score=0.9,
                language="en",
                entities={}
            ),
            embedding=[0.1, 0.2, 0.3]
        )
    ]

@pytest.mark.asyncio
async def test_pg_vector_store_initialization():
    store = PgVectorStore("postgresql://test:test@localhost:5432/test")
    
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    
    mock_conn.__aenter__.return_value = mock_conn
    mock_cursor.__aenter__.return_value = mock_cursor
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    
    with patch("psycopg.AsyncConnection.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_conn
        
        await store.initialize()
        
        mock_connect.assert_called_once_with("postgresql://test:test@localhost:5432/test")
        mock_cursor.execute.assert_called_once_with("SELECT 1;")


@pytest.mark.asyncio
async def test_pg_vector_store_store_batch(mock_embedded_chunks):
    store = PgVectorStore("postgresql://test:test@localhost:5432/test")
    
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    
    mock_conn.__aenter__.return_value = mock_conn
    mock_cursor.__aenter__.return_value = mock_cursor
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    
    with patch("psycopg.AsyncConnection.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_conn
        
        await store.store_batch(mock_embedded_chunks)
        
        mock_cursor.executemany.assert_called_once()
        
        # Check args passed to executemany
        call_args = mock_cursor.executemany.call_args
        query, params = call_args[0]
        
        assert "INSERT INTO kb_chunks" in query
        assert len(params) == 1
        
        param_tuple = params[0]
        assert param_tuple[0] == "Test text content"
        assert param_tuple[1] == "[0.1,0.2,0.3]"
        assert param_tuple[2] == "http://test.com"
        assert param_tuple[3] == "Test Title"
        assert param_tuple[4] == "blog" # Assuming SourceType.BLOG.value is "blog"
        assert param_tuple[5] == [] # Tags
        assert param_tuple[6] is True # Argentina specific is True since jurisdiction has ARGENTINA
        assert param_tuple[7] == 0 # Chunk index parsed from test_doc_0
        
        mock_conn.commit.assert_called_once()
