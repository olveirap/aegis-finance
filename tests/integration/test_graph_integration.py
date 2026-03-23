"""Integration tests for the full Aegis Graph flow."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from aegis.graph import aegis_graph, process_query
from aegis.graph.router import QueryType


@pytest.mark.asyncio
@patch("aegis.graph.router.router_node", new_callable=AsyncMock)
@patch("aegis.graph.sql_flow.sql_flow_node", new_callable=AsyncMock)
@patch("aegis.graph.staleness.staleness_node", new_callable=AsyncMock)
async def test_graph_flow_sql_to_staleness(mock_stale, mock_sql, mock_router):
    # This test verifies that the graph can be partially mocked if we were building it.
    # But since aegis_graph is compiled at import, we mostly rely on internal mocks.
    pass

@pytest.mark.asyncio
async def test_full_graph_execution_mocked():
    """Test the compiled graph by mocking all external side effects."""
    
    # 1. Mock Router
    # We must provide all fields required by RouterOutputData
    router_json = '{"query_type": "PERSONAL_FINANCIAL", "route": "sql", "requires_cloud": false, "requires_tools": false, "reasoning": "test"}'
    
    with patch("aegis.graph.router._call_llama_cpp", new_callable=AsyncMock) as mock_route_llm:
        mock_route_llm.return_value = router_json
        
        # 2. Mock SQL LLM and DB
        with patch("aegis.graph.sql_flow._call_llm", new_callable=AsyncMock) as mock_sql_llm, \
             patch("aegis.graph.sql_flow._embed_text", new_callable=AsyncMock) as mock_embed, \
             patch("aegis.graph.sql_flow.get_connection") as mock_conn_sql:
            
            mock_sql_llm.return_value = "```sql\nSELECT 1\n```"
            mock_embed.return_value = [0.1] * 768
            
            # Mock DB
            m_conn = MagicMock()
            m_cur = AsyncMock()
            m_cur.description = [MagicMock(name="col1")]
            m_cur.description[0].name = "test_col"
            m_cur.fetchall.return_value = [[123]]
            m_conn.cursor.return_value.__aenter__.return_value = m_cur
            mock_conn_sql.return_value.__aenter__.return_value = m_conn
            
            # 3. Mock Staleness DB
            with patch("aegis.graph.staleness.get_connection") as mock_conn_stale:
                m_conn_s = MagicMock()
                m_cur_s = AsyncMock()
                m_cur_s.fetchone.return_value = [None] 
                m_conn_s.cursor.return_value.__aenter__.return_value = m_cur_s
                mock_conn_stale.return_value.__aenter__.return_value = m_conn_s
                
                # Execute
                result = await process_query("What is my balance?")
                
                assert "sql_result" in result
                assert result["sql_result"][0]["test_col"] == 123
                assert "Query executed successfully" in result["final_answer"]

@pytest.mark.asyncio
async def test_full_graph_rag_path_mocked():
    """Test the RAG path by mocking the router and RAG nodes."""
    
    router_json = '{"query_type": "MARKET_KNOWLEDGE", "route": "rag", "requires_cloud": false, "requires_tools": false, "reasoning": "test"}'
    
    with patch("aegis.graph.router._call_llama_cpp", new_callable=AsyncMock) as mock_route_llm:
        mock_route_llm.return_value = router_json
        
        # Mock Privacy, Retriever, and Cloud LLM
        with patch("aegis.graph.privacy.RiskScorer.calculate_risk", return_value=0.01), \
             patch("aegis.graph.privacy.SemanticScrubber.scrub", side_effect=lambda x, m: x), \
             patch("aegis.rag.retriever.Retriever.retrieve", new_callable=AsyncMock) as mock_retrieve, \
             patch("aegis.common.cloud_llm.CloudLLMClient.generate", new_callable=AsyncMock) as mock_gen, \
             patch("aegis.graph.staleness.check_staleness", new_callable=AsyncMock) as mock_stale:
            
            mock_retrieve.return_value = [{"content": "info", "source": "s", "source_title": "t"}]
            mock_gen.return_value = "This is the RAG answer."
            mock_stale.return_value = None # No staleness warning
            
            result = await process_query("What is a CEDEAR?")
            
            assert result["final_answer"] == "This is the RAG answer."
            assert "rag_chunks" in result
