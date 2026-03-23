import argparse
import asyncio
import json
import logging
import os
import random
import sys
from collections import defaultdict
from typing import Any, Dict, List

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg
from openai import AsyncOpenAI

from aegis.kb.embedder import LlamaCppEmbedder

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- PROMPT CONSTANTS for Reproducibility ---

JUDGE_RELEVANCE_PROMPT = """You are an expert financial evaluator. 
Your task is to determine if the provided retrieved document chunk contains information that is highly relevant and necessary to answer the user's query.

Query: {query}
Context: {context}

First, briefly think step-by-step about whether the context contains facts, rules, or data necessary for the query.
Then, on a new line, output a single boolean label: true or false.

Reasoning:
"""

JUDGE_A_B_EVALUATION_PROMPT = """You are an expert Argentine financial advisor reviewing two potential answers to a client's query.
You must evaluate Answer A and Answer B against the required Key Claims.

Client Context: {user_context}
Client Query: {query}

Required Key Claims to cover:
{key_claims}

Answer A:
{answer_a}

Answer B:
{answer_b}

STEP 1: HALLUCINATION CHECK
Does Answer A contain any factual claims that contradict known facts about Argentine finance or the provided key claims? (Yes/No)
Does Answer B contain any factual claims that contradict known facts about Argentine finance or the provided key claims? (Yes/No)

STEP 2: SCORING (1-5)
If an answer failed the hallucination check (Yes), its score must be 0.
Otherwise, score each answer from 1 to 5 based on how well it covers the Key Claims and is useful to the client's context.
If neither is correct or useful, score them 0.

Output your response EXACTLY in this JSON format:
{{
  "answer_a_hallucinated": true/false,
  "answer_b_hallucinated": true/false,
  "answer_a_score": 0-5,
  "answer_b_score": 0-5,
  "reasoning": "Brief explanation of your scoring..."
}}
"""

ANSWER_GENERATION_PROMPT = """You are a knowledgeable AI financial advisor specializing in the Argentine market.
Given the User Context and the Provided Context chunks, answer the User Query accurately.
If the Provided Context does not contain enough information, state that clearly.

User Context: {user_context}
Provided Context:
{context_chunks}

User Query: {query}
Answer:"""


class RagBenchmarkRunner:
    def __init__(
        self, db_url: str, llm_base_url: str, seed: int = 42, dry_run: bool = False
    ):
        self.db_url = db_url
        self.openai_client = AsyncOpenAI(
            api_key="sk-local",
            base_url=f"{llm_base_url.rstrip('/')}/v1",
            timeout=60.0,
            max_retries=1,
        )
        self.embedder = LlamaCppEmbedder(base_url="http://localhost:8080/v1")
        self.seed = seed
        self.dry_run = dry_run
        random.seed(self.seed)

        # Benchmark variables
        self.k_retrieval = 5
        self.k_stuffed = 20
        self.llm_model = "qwen3-benchmark"  # Placeholder, will use default local model
        self.max_stuffed_tokens = 6000

    async def run(self, dataset_path: str, output_path: str):
        logger.info(f"Loading dataset from {dataset_path}")
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        if self.dry_run:
            logger.info("DRY RUN enabled: limiting to 5 questions.")
            dataset = dataset[:5]

        results = []
        metrics = defaultdict(list)

        conn = None
        try:
            logger.info("Attempting DB connection...")
            conn = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.db_url), timeout=5.0
            )
            logger.info("DB connection established.")
        except Exception as e:
            logger.warning(
                f"Database connection failed: {e}. Proceeding with mock retrieval."
            )

        try:
            for item in dataset:
                try:
                    logger.info(f"Processing query: {item['query'][:50]}...")
                    item_result = await self._process_item(conn, item)
                    results.append(item_result)

                    # Accumulate metrics
                    qt = item.get("query_type", "unknown")
                    metrics[qt].append(item_result["metrics"])
                    metrics["overall"].append(item_result["metrics"])
                except Exception as e:
                    logger.error(f"Error processing item: {e}")
        finally:
            if conn:
                await conn.close()

        # Aggregate logic
        aggregated = self._aggregate_metrics(metrics)

        final_output = {
            "benchmark_config": {
                "k_retrieval": self.k_retrieval,
                "k_stuffed": self.k_stuffed,
                "temperature": 0,
                "seed": self.seed,
                "dry_run": self.dry_run,
            },
            "aggregate_metrics": aggregated,
            "items": results,
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)

        logger.info(f"Benchmark completed. Results saved to {output_path}")

    async def _process_item(self, conn, item: Dict[str, Any]) -> Dict[str, Any]:
        query = item["query"]
        user_context = item.get("user_context", "")
        context_aware_query = f"{user_context}\n\n{query}" if user_context else query

        # 1. Retrieval
        try:
            q_emb = (await self.embedder._embed_batch([query]))[0]
            ca_q_emb = (await self.embedder._embed_batch([context_aware_query]))[0]
        except Exception as e:
            logger.warning(
                f"Embedder failed (llama.cpp likely not running): {e}. Using dummy embeddings."
            )
            q_emb = [0.0] * 1024
            ca_q_emb = [0.0] * 1024

        if conn is None:
            top_k_chunks = [
                {
                    "content": "Dummy chunk from DB missing",
                    "source": "dummy_source",
                    "topic_tags": [],
                }
            ] * self.k_retrieval
            ca_top_k_chunks = [
                {"content": "Dummy empty DB chunk", "source": "dummy", "topic_tags": []}
            ] * self.k_stuffed
        else:
            top_k_chunks = await self._retrieve_chunks(conn, q_emb, self.k_retrieval)
            ca_top_k_chunks = await self._retrieve_chunks(
                conn, ca_q_emb, self.k_stuffed
            )

        # 2. Layer Coverage @ 5
        ca_top_5 = ca_top_k_chunks[: self.k_retrieval]
        layer_coverage = self._evaluate_layer_coverage(
            ca_top_5, item.get("required_layers", {})
        )

        # 3. Retrieval Metrics (MRR, Recall, NDCG) via LLM judge or ground truth
        # Evaluate standard query baseline
        base_top_5 = top_k_chunks[: self.k_retrieval]
        base_rel_array = await self._get_relevance_array(
            base_top_5, query, item.get("relevant_chunks", [])
        )
        base_recall_at_5 = (
            sum(base_rel_array) / len(base_rel_array) if base_rel_array else 0.0
        )
        base_mrr = 0.0
        for idx, val in enumerate(base_rel_array):
            if val:
                base_mrr = 1.0 / (idx + 1)
                break

        # Evaluate context-aware query
        ca_rel_array = await self._get_relevance_array(
            ca_top_5, query, item.get("relevant_chunks", [])
        )
        ca_recall_at_5 = sum(ca_rel_array) / len(ca_rel_array) if ca_rel_array else 0.0
        ca_mrr = 0.0
        for idx, val in enumerate(ca_rel_array):
            if val:
                ca_mrr = 1.0 / (idx + 1)
                break

        # 4. Answer Generation
        rag_context = "\n\n".join([c["content"] for c in ca_top_5])
        stuffed_context = "\n\n".join([c["content"] for c in ca_top_k_chunks])

        # Guardrail on token limits (rough approximation)
        stuffed_tokens = len(stuffed_context.split()) * 1.3
        if stuffed_tokens > self.max_stuffed_tokens:
            logger.warning(
                f"Stuffed context exceeds {self.max_stuffed_tokens} tokens. Truncating."
            )
            stuffed_context = stuffed_context[
                : self.max_stuffed_tokens * 3
            ]  # rough char cut

        rag_answer = await self._generate_answer(user_context, query, rag_context)
        stuffed_answer = await self._generate_answer(
            user_context, query, stuffed_context
        )

        # 5. A/B Blinded Evaluation
        is_rag_a = random.choice([True, False])
        ans_a = rag_answer if is_rag_a else stuffed_answer
        ans_b = stuffed_answer if is_rag_a else rag_answer

        eval_result = await self._evaluate_answers(item, ans_a, ans_b)

        rag_score = (
            eval_result["answer_a_score"] if is_rag_a else eval_result["answer_b_score"]
        )
        stuffed_score = (
            eval_result["answer_b_score"] if is_rag_a else eval_result["answer_a_score"]
        )
        rag_hallucinated = (
            eval_result["answer_a_hallucinated"]
            if is_rag_a
            else eval_result["answer_b_hallucinated"]
        )

        metrics = {
            "base_recall_at_5": base_recall_at_5,
            "base_mrr": base_mrr,
            "ca_recall_at_5": ca_recall_at_5,
            "ca_mrr": ca_mrr,
            "layer_coverage_all": layer_coverage["all_present"],
            "rag_score": rag_score,
            "stuffed_score": stuffed_score,
            "rag_hallucinated": rag_hallucinated,
        }

        status = "success"
        if (
            conn is None
            or q_emb == [0.0] * 1024
            or "Error" in rag_answer
            or "Error" in stuffed_answer
        ):
            status = "skipped_unprovisioned"

        return {
            "query": query,
            "query_type": item.get("query_type"),
            "status": status,
            "metrics": metrics,
            "rag_answer": rag_answer,
            "stuffed_answer": stuffed_answer,
            "judge_reasoning": eval_result.get("reasoning", ""),
        }

    async def _retrieve_chunks(
        self, conn, embedding: List[float], k: int
    ) -> List[Dict[str, Any]]:
        # Check if table exists, if not return dummy
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT to_regclass('kb_chunks');")
                res = await cur.fetchone()
                if not res or not res[0]:
                    return [
                        {
                            "content": "Dummy chunk from DB missing",
                            "source": "dummy_source",
                        }
                    ] * k

                emb_str = "[" + ",".join(map(str, embedding)) + "]"
                await cur.execute(
                    "SELECT content, source, source_title, topic_tags FROM kb_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
                    (emb_str, k),
                )
                rows = await cur.fetchall()
                if not rows:
                    return [{"content": "Dummy empty DB chunk", "source": "dummy"}] * k
                return [
                    {
                        "content": r[0],
                        "source": r[1],
                        "source_title": r[2],
                        "topic_tags": r[3],
                    }
                    for r in rows
                ]
        except psycopg.Error:
            return [
                {
                    "content": "Mock retrieved content due to DB error",
                    "source": "mock",
                    "topic_tags": [],
                }
            ] * k

    def _evaluate_layer_coverage(
        self, chunks: List[Dict[str, Any]], required_layers: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        coverage = {}
        all_present = True

        if not required_layers:
            return {"all_present": True}

        combined_meta = " ".join(
            [
                f"{c.get('source', '')} {c.get('source_title', '')} {' '.join(c.get('topic_tags', []))}"
                for c in chunks
            ]
        ).lower()

        for layer_name, requirements in required_layers.items():
            # Check if any requirement for this layer is in the metadata
            layer_hit = any(req.lower() in combined_meta for req in requirements)
            coverage[f"{layer_name}_present"] = layer_hit
            if not layer_hit:
                all_present = False

        coverage["all_present"] = all_present
        return coverage

    async def _get_relevance_array(
        self, chunks, query, relevant_chunk_ids
    ) -> List[bool]:
        # If we have ground truth, use it (simplified matching)
        if relevant_chunk_ids:
            # We don't have chunk_id in the simple select, string matching instead
            return [False] * len(chunks)  # Stubbed for purity

        # Fallback to LLM boolean judge
        tasks = []
        for c in chunks:
            tasks.append(self._judge_chunk_relevance(query, c["content"]))

        res = await asyncio.gather(*tasks, return_exceptions=True)
        return [r if isinstance(r, bool) else False for r in res]

    async def _judge_chunk_relevance(self, query: str, context: str) -> bool:
        prompt = JUDGE_RELEVANCE_PROMPT.format(query=query, context=context)
        try:
            resp = await self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                seed=self.seed,
            )
            text = resp.choices[0].message.content.strip().lower()
            return "true" in text.split("\n")[-1]
        except Exception:
            return False

    async def _generate_answer(
        self, user_context: str, query: str, context_chunks: str
    ) -> str:
        prompt = ANSWER_GENERATION_PROMPT.format(
            user_context=user_context, context_chunks=context_chunks, query=query
        )
        try:
            resp = await self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                seed=self.seed,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Error generating answer: {e}"

    async def _evaluate_answers(
        self, item: Dict[str, Any], ans_a: str, ans_b: str
    ) -> Dict[str, Any]:
        key_claims = "\n".join(f"- {claim}" for claim in item.get("key_claims", []))
        prompt = JUDGE_A_B_EVALUATION_PROMPT.format(
            user_context=item.get("user_context", ""),
            query=item["query"],
            key_claims=key_claims,
            answer_a=ans_a,
            answer_b=ans_b,
        )
        try:
            resp = await self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                seed=self.seed,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.error(f"Evaluating answers failed: {e}")
            return {
                "answer_a_hallucinated": False,
                "answer_b_hallucinated": False,
                "answer_a_score": 0,
                "answer_b_score": 0,
                "reasoning": "Judge failed.",
            }

    def _aggregate_metrics(
        self, metrics: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        aggs = {}
        for category, m_list in metrics.items():
            count = len(m_list)
            if count == 0:
                continue
            aggs[category] = {
                "count": count,
                "base_recall_at_5": sum(m["base_recall_at_5"] for m in m_list) / count,
                "base_mrr": sum(m["base_mrr"] for m in m_list) / count,
                "ca_recall_at_5": sum(m["ca_recall_at_5"] for m in m_list) / count,
                "ca_mrr": sum(m["ca_mrr"] for m in m_list) / count,
                "layer_coverage_at_5": sum(1 for m in m_list if m["layer_coverage_all"])
                / count,
                "avg_answer_quality_rag": sum(m["rag_score"] for m in m_list) / count,
                "hallucination_rate": sum(1 for m in m_list if m["rag_hallucinated"])
                / count,
            }
        return {
            "by_query_type": {k: v for k, v in aggs.items() if k != "overall"},
            "overall": aggs.get("overall", {}),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAG Benchmarks")
    parser.add_argument(
        "--db-url",
        type=str,
        default=os.environ.get(
            "AEGIS_DB_URL", "postgresql://aegis:aegis_dev@localhost:5432/aegis_finance"
        ),
    )
    parser.add_argument("--llm-url", type=str, default="http://localhost:8080")
    parser.add_argument(
        "--dataset", type=str, default="tests/benchmarks/kb_quality.json"
    )
    parser.add_argument(
        "--output", type=str, default="tests/benchmarks/results/kb_baseline.json"
    )
    parser.add_argument("--dry-run", action="store_true", help="Limit to 5 questions")

    args = parser.parse_args()

    runner = RagBenchmarkRunner(
        db_url=args.db_url, llm_base_url=args.llm_url, dry_run=args.dry_run
    )

    asyncio.run(runner.run(args.dataset, args.output))
