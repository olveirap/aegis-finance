"""Tests for PostgreSQL Vector Storage backend."""

import pytest
from unittest.mock import patch, MagicMock

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
                jurisdiction=["AR"],
                topic_tags=[],
                relevance_score=0.9,
                language="en",
                entities={},
            ),
            embedding=[0.1, 0.2, 0.3],
        )
    ]


@pytest.mark.asyncio
@pytest.mark.asyncio
@patch("aegis.kb.storage.ConnectionPool")
async def test_pg_vector_store_initialization(mock_pool):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.__enter__.return_value = mock_conn
    mock_cursor.__enter__.return_value = mock_cursor
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    mock_pool_instance = MagicMock()
    mock_pool_instance.connection.return_value.__enter__.return_value = mock_conn
    mock_pool.return_value = mock_pool_instance

    store = PgVectorStore("postgresql://test:test@localhost:5432/test")

    await store.initialize()

    mock_pool.assert_called_once_with(
        conninfo="postgresql://test:test@localhost:5432/test",
        min_size=1,
        max_size=10,
        open=False,
    )
    mock_cursor.execute.assert_called_once_with("SELECT 1;")


@pytest.mark.asyncio
@patch("aegis.kb.storage.ConnectionPool")
async def test_pg_vector_store_store_batch(mock_pool, mock_embedded_chunks):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.__enter__.return_value = mock_conn
    mock_cursor.__enter__.return_value = mock_cursor
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    mock_pool_instance = MagicMock()
    mock_pool_instance.connection.return_value.__enter__.return_value = mock_conn
    mock_pool.return_value = mock_pool_instance

    store = PgVectorStore("postgresql://test:test@localhost:5432/test")

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
    assert param_tuple[4] == "blog"  # Assuming SourceType.BLOG.value is "blog"
    assert param_tuple[5] == []  # Tags
    assert (
        param_tuple[6] is True
    )  # Argentina specific is True since jurisdiction has AR
    assert param_tuple[7] == 0  # Chunk index parsed from test_doc_0

    mock_conn.commit.assert_called_once()
