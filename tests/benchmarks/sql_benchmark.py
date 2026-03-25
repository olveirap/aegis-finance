# SPDX-License-Identifier: MIT
"""Benchmark script for Text-to-SQL accuracy.

Evaluates the sql_flow_node against a golden set of 20 queries.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pandas as pd
from aegis.graph.sql_flow import sql_flow_node
from aegis.db.connection import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SQLBenchmarkRunner:
    def __init__(self, dataset_path: str, output_path: str):
        self.dataset_path = dataset_path
        self.output_path = output_path

    async def run(self):
        logger.info(f"Loading golden set from {self.dataset_path}")
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        results = []
        metrics = {
            "total": len(dataset),
            "exact_match": 0,
            "execution_match": 0,
            "errors": 0,
        }

        for item in dataset:
            query = item["query"]
            golden_sql = item["golden_sql"]
            logger.info(f"Evaluating query: {query}")

            try:
                # 1. Generate SQL via flow node
                state = {"query": query}
                # We need to mock the LLM if we want a pure code test,
                # but for a benchmark we usually run against the real LLM.
                # Assuming llama.cpp is running.
                node_result = await sql_flow_node(state)

                # Check if we got a final_answer (error) or sql_result
                # Since sql_flow_node doesn't return the SQL string in the state,
                # we'd need to modify it or extract it.
                # Let's assume for benchmark we want to see the SQL.
                # I will modify sql_flow_node slightly to include 'generated_sql' in state.

                # For now, let's just compare the execution results if sql_result exists
                if "sql_result" in node_result:
                    gen_data = node_result["sql_result"]
                    # 2. Get golden results
                    golden_data = await self._execute_sql(golden_sql)

                    # 3. Compare
                    is_match = self._compare_results(gen_data, golden_data)
                    if is_match:
                        metrics["execution_match"] += 1

                    results.append(
                        {
                            "query": query,
                            "golden_sql": golden_sql,
                            "match": is_match,
                            "error": None,
                        }
                    )
                else:
                    metrics["errors"] += 1
                    results.append(
                        {
                            "query": query,
                            "golden_sql": golden_sql,
                            "match": False,
                            "error": node_result.get("final_answer", "Unknown error"),
                        }
                    )

            except Exception as e:
                logger.error(f"Failed to evaluate query '{query}': {e}")
                metrics["errors"] += 1
                results.append(
                    {
                        "query": query,
                        "golden_sql": golden_sql,
                        "match": False,
                        "error": str(e),
                    }
                )

        # Calculate accuracy
        metrics["accuracy"] = (
            metrics["execution_match"] / metrics["total"] if metrics["total"] > 0 else 0
        )

        final_output = {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "details": results,
        }

        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)

        logger.info(f"Benchmark completed. Accuracy: {metrics['accuracy']:.2%}")

    async def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
        try:
            async with get_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql)
                    columns = [desc.name for desc in cur.description]
                    rows = await cur.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return []

    def _compare_results(
        self, gen: List[Dict[str, Any]], golden: List[Dict[str, Any]]
    ) -> bool:
        if len(gen) != len(golden):
            return False

        # Compare as DataFrames for easier handling of column order and types
        df_gen = pd.DataFrame(gen)
        df_golden = pd.DataFrame(golden)

        if df_gen.empty and df_golden.empty:
            return True

        try:
            # Reorder columns to match if necessary
            df_gen = df_gen[df_golden.columns]
            pd.testing.assert_frame_equal(
                df_gen, df_golden, check_dtype=False, check_exact=False
            )
            return True
        except (AssertionError, KeyError):
            return False


if __name__ == "__main__":
    runner = SQLBenchmarkRunner(
        dataset_path="tests/benchmarks/data/sql_golden.json",
        output_path="tests/benchmarks/results/sql_results.json",
    )
    asyncio.run(runner.run())
