"""QA tests to verify the KB population process.

These tests assert against a live PostgreSQL pgvector database to ensure
that the knowledge base was populated successfully and similarity searches
work correctly.
"""

import os
import pytest
import psycopg

from aegis.kb.embedder import LlamaCppEmbedder
from aegis.kb.storage import get_storage

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("AEGIS_DB_URL"),
        reason="Requires live Postgres/pgvector; set AEGIS_DB_URL to enable.",
    ),
]

DB_URL = os.environ.get(
    "AEGIS_DB_URL", "postgresql://aegis:aegis_dev@localhost:5432/aegis_finance"
)


@pytest.mark.asyncio
async def test_kb_population_count():
    """Assert the kb_chunks table has >= 500 records."""
    store = get_storage(DB_URL)
    count = await store.get_count()

    # QA Criteria: >= 500 quality chunks stored
    # Note: If running this test on an empty DB, it will fail.
    # It's intended to be run post-ingestion.
    assert count >= 500, f"Expected at least 500 chunks, found {count}"


@pytest.mark.asyncio
async def test_kb_similarity_search():
    """Execute real similarity search query and verify top-k relevance."""

    # 1. Embed a test query using the local embedder
    embedder = LlamaCppEmbedder()
    test_query = "Qué es el dólar MEP?"
    try:
        embeddings = await embedder._embed_batch([test_query])
        query_emb = embeddings[0]
    except Exception as e:
        pytest.skip(f"Embedder or llama.cpp not available for query generation: {e}")

    # 2. Run pgvector similarity search
    query = """
        SELECT content, source_title, 1 - (embedding <=> %s::vector) AS cosine_similarity
        FROM kb_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT 5;
    """

    vector_literal = "[" + ",".join(map(str, query_emb)) + "]"

    results = []
    try:
        async with await psycopg.AsyncConnection.connect(DB_URL) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (vector_literal, vector_literal))
                results = await cur.fetchall()
    except Exception as e:
        pytest.fail(f"Failed to query database: {e}")

    assert len(results) > 0, "No results returned from similarity search."

    # 3. Verify top-k relevance: At least the top result should have a high similarity score
    # Cosine similarity is 1 - cosine distance (<=>)
    top_score = results[0][2]
    assert top_score > 0.5, (
        f"Top result relevance ({top_score}) is unexpectedly low for a basic query."
    )

    # And it should contain relevant finance keywords
    content_lower = results[0][0].lower()
    has_keywords = any(
        kw in content_lower
        for kw in ["mep", "dólar", "bolsa", "bono", "tipo de cambio"]
    )
    assert has_keywords, (
        f"Top result did not contain expected financial keywords: {content_lower[:200]}..."
    )
