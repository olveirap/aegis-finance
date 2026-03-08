# SPDX-License-Identifier: MIT
"""CLI to orchestrate Knowledge Base Ingestion Pipeline."""

import argparse
import asyncio
import logging
import sys
from pydantic import BaseModel

from aegis.kb.embedder import LlamaCppEmbedder
from aegis.kb.ingestion.registry import SourceRegistry
from aegis.kb.ingestion.runner import IngestionRunner
from aegis.kb.pipeline import KBPipeline
from aegis.kb.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class KBIngestionResult(BaseModel):
    """Result summary of the KB ingestion run."""
    processed_chunks: int = 0
    stored_chunks: int = 0
    errors: int = 0


async def run_kb_ingest(registry_paths: list[str]) -> KBIngestionResult:
    """Run the end-to-end knowledge base ingestion logic.
    
    1. Reads YAML sources.
    2. Runs extractors/connectors.
    3. Runs the quality pipeline (chunking, tagging).
    4. Embeds chunks via local llama.cpp.
    5. Stores embeddings safely into Postgres.
    """
    pipeline = KBPipeline()
    embedder = LlamaCppEmbedder()
    storage = get_storage()
    
    await storage.initialize()
    
    result = KBIngestionResult()
    
    for path in registry_paths:
        logger.info(f"Loading registry from: {path}")
        registry = SourceRegistry.load(path)
        runner = IngestionRunner(registry)
        
        for name, config in registry.sources.items():
            logger.info(f"=== Starting source: {name} ===")
            try:
                # Accumulate raw docs to allow cross-document semantic dedup if desired,
                # but to avoid OOM we will process per document.
                async for raw_doc in runner.run_source_pipeline(config):
                    # 1. Quality Pipeline
                    try:
                        chunks = pipeline.process(raw_doc)
                        if not chunks:
                            continue
                            
                        # 2. Embedding
                        embedded = await embedder.embed(chunks)
                        result.processed_chunks += len(chunks)
                        
                        if not embedded:
                            continue
                            
                        # 3. Storage
                        await storage.store_batch(embedded)
                        result.stored_chunks += len(embedded)
                        
                    except Exception as e:
                        logger.error(f"Error processing document {raw_doc.source_url}: {e}")
                        result.errors += 1
                        
            except Exception as e:
                logger.error(f"Source pipeline {name} failed: {e}")
                result.errors += 1
                
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="KB Ingestion Pipeline Orchestrator")
    parser.add_argument(
        "cmd", 
        choices=["ingest"], 
        help="Command to run."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        help="Paths to one or more YAML source definition files."
    )
    args = parser.parse_args()
    
    if args.cmd == "ingest":
        try:
            result = asyncio.run(run_kb_ingest(args.sources))
            logger.info(f"Ingestion Complete: {result.model_dump_json(indent=2)}")
            if result.errors > 0:
                logger.warning(f"Finished with {result.errors} errors.")
                sys.exit(1)
        except KeyboardInterrupt:
            logger.info("Ingestion aborted by user.")
            sys.exit(130)
        except Exception as e:
            logger.critical(f"Unhandled fatal error: {e}")
            sys.exit(2)

if __name__ == "__main__":
    main()
