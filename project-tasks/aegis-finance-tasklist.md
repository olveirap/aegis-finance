# Aegis Finance — Phased Task List
**Orchestrated by:** Agents Orchestrator  
**Date:** 2026-03-06 | **Status:** Planning

---

## Pipeline Overview

```
Phase 0: KB Curation ─┐
     (Weeks 1–3)      │──▶ Phase 2: Intelligence ──▶ Phase 3: MVP
Phase 1: Data Found. ─┘        (Weeks 4–7)           (Weeks 8–10)
     (Weeks 1–3)
```

Phases 0 and 1 run **in parallel**. Phase 2 requires both to complete.

Each phase follows the Orchestrator workflow:
`PM → Architecture → [Developer ↔ QA loop] → Integration`

---

## Phase 0: Knowledge Base Data Gathering (Milestone 0, parallel to M1)

> **Focus:** Scrape, curate, and structure financial knowledge for RAG. Note: Initial focus is on pgvector, but laying groundwork for a Hybrid RAG with a Graph Database.
> **Exit Criteria:** pgvector contains quality-gated, deduplicated, ontology-tagged embeddings from >= 5 source types, plus extracted entities/relations. RAG benchmarks pass.
> **Specialist Roles:** Data Engineers, RAG Specialists, Ontology Experts.

### [ ] Task 0.1 — Ontology & Taxonomy Design
**Agent:** AI Engineer (Ontology Expert role)  
**Description:** Define the topic taxonomy, entity relationships (for future Graph DB), and metadata schema for the knowledge base.  
**Deliverables:**
- `src/aegis/kb/ontology.py` — Topic taxonomy and Graph node/edge definitions
  - Personal Finance: budgeting, saving, emergency fund, debt management
  - Investing: stocks, bonds, CEDEARs, FCIs, ETFs, crypto
  - Argentine-specific: ganancias, bienes personales, MEP/CCL, inflación, plazo fijo
  - Regulations: AFIP, BCRA, CNV, UIF
  - Real Estate: mortgage, rental, property tax
- `src/aegis/kb/metadata.py` — Metadata schema for KB chunks (source, type, date, tags, language, relevance_score)
- `data/knowledge/taxonomy.yaml` — YAML export of taxonomy for config/tooling

**QA:** Taxonomy covers all source categories. Metadata schema validates against sample data.

---

### [ ] Task 0.2 — Source Scrapers
**Agent:** Backend Architect (Data Engineer role)  
**Description:** Per-source adapters to fetch raw content from web sources.  
**Deliverables:**
- `src/aegis/kb/scrapers/base.py` — `BaseScraper` ABC with `scrape() → list[RawDocument]`
- `src/aegis/kb/scrapers/blog.py` — HTML blog scraper (BeautifulSoup / trafilatura)
- `src/aegis/kb/scrapers/reddit.py` — Reddit scraper (PRAW / asyncpraw for r/merval, r/personalfinance, r/argentina)
- `src/aegis/kb/scrapers/youtube.py` — YouTube transcript extractor (Whisper via llama.cpp or youtube-transcript-api fallback)
- `src/aegis/kb/scrapers/regulation.py` — Argentine regulatory document scraper (AFIP, BCRA, CNV PDFs/HTML)
- `src/aegis/kb/scrapers/book_summarizer.py` — Book content summarizer (structured "Tips & Rules" extraction, never full text)
- Rate limiting and retry logic per source
- Raw text output to `data/knowledge/raw/` (gitignored)

**QA:** Each scraper fetches ≥ 10 documents from its source. Reddit scraper handles rate limits. YouTube transcripts are extractable. Copyright compliance: no full book text stored.

---

### [ ] Task 0.3 — Deduplication & Quality Pipeline
**Agent:** AI Engineer (RAG Specialist role)  
**Description:** Quality filtering, deduplication, and entity extraction.  
**Deliverables:**
- `src/aegis/kb/pipeline.py` — End-to-end KB processing pipeline
  - Content hash deduplication (SHA-256)
  - Semantic deduplication (cosine similarity > 0.95 = duplicate)
  - Minimum length filter (< 50 tokens = discard)
  - Language detection (keep AR/ES and EN only)
  - Relevance scoring against ontology taxonomy
- `src/aegis/kb/chunker.py` — Configurable chunking (512 tokens, 64 overlap)
- `src/aegis/kb/tagger.py` — Automatic ontology tagging using Qwen 3.5 (via llama.cpp)
- `src/aegis/kb/extractor.py` — Entity and relationship extraction (prep for Graph DB)
- Source attribution preserved in every chunk's metadata

**QA:** Duplicate content is rejected. Low-quality content is filtered. Tags and extracted entities match expected ontology for test documents.

---

### [ ] Task 0.4 — KB Embedding & Storage
**Agent:** AI Engineer (RAG Specialist role)  
**Description:** Embed curated chunks and store in pgvector (with optional relational fallback for Graph DB entities).  
**Deliverables:**
- `src/aegis/kb/embedder.py` — Batch embedding via Qwen3-embedding (llama.cpp)
  - Qwen3-VL-Embedding fallback for content with images/OCR
  - Batch processing with progress tracking
- Integration with `kb_chunks` table (DDL spec)
- `make kb-ingest` command to run full pipeline: scrape → process → embed → store
- Provenance tracking: every chunk links back to source URL/title

**QA:** ≥ 500 quality chunks stored in pgvector. Embedding dimensions = 1024. Similarity search returns relevant results for test queries.

---

### [ ] Task 0.5 — RAG Knowledge Benchmarks
**Agent:** AI Engineer (RAG Specialist role)  
**Description:** Benchmark suite to measure RAG quality over the curated KB.  
**Deliverables:**
- `tests/benchmarks/kb_quality.json` — 50+ question/answer pairs covering:
  - General personal finance knowledge
  - Argentine-specific regulations (AFIP, bienes personales)
  - Investment mechanics (CEDEARs, FCIs, MEP)
  - Edge cases (multi-language, outdated info)
- `tests/benchmarks/rag_benchmark.py` — Automated RAG quality benchmarks
  - Retrieval metrics: Recall@5, NDCG@5, MRR
  - Answer quality: human-eval format + LLM-as-judge scoring
  - RAG vs. context-stuffing comparison (per project spec)
- Results output to `tests/benchmarks/results/kb_baseline.json`

**QA:** Benchmark runner completes without errors. Baseline metrics established. RAG vs. context-stuffing comparison documented.

---

## Phase 1: Data Foundation (Milestone 1)

> **Focus:** Database, Docker, parsers, synthetic data. No LLM integration yet.
> **Exit Criteria:** `docker-compose up` → populated DB → parser ingests a synthetic CSV → tests pass.

### [ ] Task 1.1 — Project Scaffolding
**Agent:** Backend Architect  
**Description:** Initialize Python project with `pyproject.toml`, directory structure per setup spec, `Makefile`, and `config.yaml` loader.  
**Deliverables:**
- `pyproject.toml` with dependency groups (core, dev, test)
- `src/aegis/__init__.py` and all module `__init__.py` files
- `src/aegis/config.py` — YAML config loader with env var interpolation
- `config.yaml` — template with all sections
- `Makefile` — common commands (`make setup`, `make test`, `make lint`, `make db-up`)
- `.gitignore` with Python, IDE, and env file patterns

**QA:** `pip install -e ".[dev]"` succeeds, `make lint` passes, config loads without error.

---

### [ ] Task 1.2 — Docker + PostgreSQL + pgvector
**Agent:** DevOps Automator  
**Description:** Create `docker-compose.yml` and SQL init scripts for PostgreSQL with pgvector.  
**Deliverables:**
- `docker-compose.yml` — pgvector/pgvector:pg16 service
- `sql/001_schema.sql` — All base table DDLs from DDL spec
- `sql/002_views.sql` — All curated view definitions
- `src/aegis/db/connection.py` — Connection pool management with `psycopg` (pool)

**QA:** `docker-compose up -d` → `psql` connects → tables exist → views queryable → `docker-compose down` clean.

---

### [ ] Task 1.3 — Synthetic Data Generator
**Agent:** Backend Architect  
**Description:** Python script to populate the sandbox with realistic Argentine financial data.  
**Deliverables:**
- `data/synthetic/generate.py` — Faker + NumPy generator
  - 3–5 accounts (checking ARS, savings USD, crypto wallet, brokerage)
  - 6 months of transactions (200–400/month, realistic categories)
  - Exchange rates with MEP/official spread simulation
  - Sample assets (CEDEARs, ETFs, USDT)
  - Income sources (salary, freelance)
- `sql/003_seed_synthetic.sql` — Optional SQL-based alternative seed

**QA:** `python data/synthetic/generate.py` → `SELECT COUNT(*) FROM transactions` returns > 1000 rows → views return sensible aggregates.

---

### [ ] Task 1.4 — Statement Parser Framework
**Agent:** Backend Architect  
**Description:** Abstract parser interface and first concrete CSV parser.  
**Deliverables:**
- `src/aegis/parsers/base.py` — `BaseParser` ABC with `parse(file_path) → list[Transaction]`
- `src/aegis/parsers/bank_csv.py` — Generic CSV parser with configurable column mapping
- Duplicate detection via `(account_id, date, amount, merchant_raw)` constraint
- Import batch tracking via `import_batches` table

**QA:** Parser ingests a synthetic CSV, inserts rows, duplicate re-import is rejected, import batch is recorded.

---

### [ ] Task 1.5 — Transaction Categorizer (Rule-Based Baseline)
**Agent:** AI Engineer  
**Description:** Initial rule-based categorizer with keyword matching. LLM categorizer deferred to Phase 2.  
**Deliverables:**
- `src/aegis/parsers/categorizer.py`
  - `RuleBasedCategorizer` — keyword-to-category mapping (e.g., "supermercado" → Food)
  - Confidence scoring (1.0 for exact keyword match, 0.5 for partial)
  - HITL flagging when `score < 0.85` or multi-label conflict
  - `is_flagged = True` on ambiguous transactions
- `data/category_rules.yaml` — keyword → category mapping file

**QA:** Categorizer assigns correct categories to known merchants, flags ambiguous ones, confidence scores are in valid range.

---

### [ ] Task 1.6 — Phase 1 Tests
**Agent:** Backend Architect  
**Description:** Test suite for all Phase 1 deliverables.  
**Deliverables:**
- `tests/unit/test_config.py` — Config loader tests
- `tests/unit/test_parser.py` — CSV parser tests
- `tests/unit/test_categorizer.py` — Categorizer tests
- `tests/integration/test_db.py` — Database connection and basic queries
- `tests/integration/test_import_pipeline.py` — End-to-end: CSV → parse → categorize → DB insert

**QA:** `make test` → all tests pass, coverage report generated.

---

## Phase 2: Intelligence Layer (Milestone 2)

> **Focus:** LangGraph, LLM integration, RAG, privacy, benchmarks.
> **Exit Criteria:** User can type a financial question → system routes, queries DB, retrieves knowledge, scrubs PII, and returns an answer.

### [ ] Task 2.1 — LangGraph Orchestrator Setup
**Agent:** AI Engineer  
**Description:** Create the main LangGraph state machine with router node.  
**Deliverables:**
- `src/aegis/graph/__init__.py` — Graph builder and state definition
- `src/aegis/graph/router.py` — Router node with query type classification
  - Uses Qwen 3.5 via llama.cpp for classification
  - Output: `{ route, query_type, requires_cloud, requires_tools }`
- State schema: `AegisState` with query, history, sql_result, rag_chunks, privacy_output, tool_results

**QA:** Router correctly classifies 10+ test queries into 5 categories (incl. RESEARCH). Unit tests with mocked llama.cpp responses.

---

### [ ] Task 2.2 — Text-to-SQL Flow
**Agent:** AI Engineer  
**Description:** SQL generation with 4-step validation loop.  
**Deliverables:**
- `src/aegis/graph/sql_flow.py`
  - Prompt construction with injected view definitions
  - View selection via pgvector similarity on view descriptions
  - 4-step validation: syntax → schema → EXPLAIN → sanity check
  - Max 3 retries with structured error feedback
  - Currency mixing warning
- Allowed-views whitelist enforcement

**QA:** Generates correct SQL for 10+ natural language queries against curated views. Rejects invalid SQL. Currency mixing triggers warning.

---

### [ ] Task 2.3 — Privacy Middleware
**Agent:** AI Engineer  
**Description:** Two-pass PII scrubbing with risk scoring.  
**Deliverables:**
- `src/aegis/privacy/regex_scrubber.py` — Pass 1 regex patterns (CUIT, CBU, ARS, USD, email, names)
- `src/aegis/privacy/semantic_scrubber.py` — Pass 2 LLM semantic audit
- `src/aegis/privacy/redaction_map.py` — SQLite session-scoped storage
- `src/aegis/privacy/risk_scorer.py` — Presidio-based residual PII scanner
- `src/aegis/graph/privacy.py` — LangGraph node wrapping the pipeline
- Range bucket replacement (not `[REDACTED]`) per config thresholds

**QA:** Scrubs known PII patterns, applies range buckets, risk score < 0.05 for clean text, blocks cloud call and tool usage when risk > 0.05.

---

### [ ] Task 2.3b — Anonymized Browser & Search Tools
**Agent:** AI Engineer  
**Description:** Agent tools for web search and browser browsing that route through Privacy Node.  
**Deliverables:**
- `src/aegis/tools/web_search.py` — Web search tool that anonymizes the query via Privacy Node before searching
- `src/aegis/tools/browser.py` — Browser tool that anonymizes navigation queries via Privacy Node
- `src/aegis/graph/research_flow.py` — LangGraph RESEARCH flow: Privacy Node → Tool Execution → Synthesis
- Integration with LangGraph state: tool results stored in `AegisState.tool_results`

**QA:** Search query containing PII is anonymized before execution. Browser queries containing financial context are scrubbed. RESEARCH flow produces synthesized results.

---

### [ ] Task 2.4 — Hybrid RAG Pipeline
**Agent:** AI Engineer  
**Description:** Hybrid knowledge base ingestion and retrieval pipeline (Vector + Graph traversal).  
**Deliverables:**
- `src/aegis/rag/ingestion.py` — Document chunking (512 tokens, 64 overlap) + Qwen3-embedding via llama.cpp
- `src/aegis/rag/retriever.py` — Hybrid retrieval: pgvector similarity + Graph knowledge traversal
- `src/aegis/rag/reranker.py` — Cross-encoder reranking (local model)
- `src/aegis/graph/rag_flow.py` — LangGraph node for Hybrid RAG retrieval
- `data/knowledge/` — Seed with 5–10 curated Argentine finance documents

**QA:** Ingests sample documents, embeds correctly, retrieves relevant chunks for test queries, reranker improves ordering.

---

### [ ] Task 2.5 — LLM Categorizer (SLM-Based Upgrade)
**Agent:** AI Engineer  
**Description:** Replace rule-based categorizer with SLM-based classifier.  
**Deliverables:**
- Update `src/aegis/parsers/categorizer.py` with `SLMCategorizer`
  - Uses Qwen 3.5 via llama.cpp for classification
  - Multi-label output with confidence scores
  - Fallback to rule-based if llama.cpp server is unavailable
- Few-shot prompt with user's correction history

**QA:** SLM categorizer matches or exceeds rule-based accuracy on test dataset. HITL triggers correctly for low-confidence results.

---

### [ ] Task 2.6 — Staleness Guardrail
**Agent:** Backend Architect  
**Description:** Automated freshness checks on transaction data.  
**Deliverables:**
- `src/aegis/graph/staleness.py` — LangGraph node checking `last_transaction_import`
  - Warning threshold: configurable (default 30 days)
  - Warning type: banner injection + answer disclaimer
  - Does NOT block queries

**QA:** Correctly triggers warning when data is older than threshold. Does not block queries. Warning text is appended to SQL-based answers.

---

### [ ] Task 2.7 — Benchmark Suite
**Agent:** AI Engineer  
**Description:** Quality benchmarks for Text-to-SQL and RAG.  
**Deliverables:**
- `tests/benchmarks/qa_finance.json` — 30+ question/answer pairs for finance Q&A
- `tests/benchmarks/sql_accuracy.json` — 20+ NL→SQL golden pairs
- `tests/benchmarks/benchmark_runner.py` — Automated benchmark execution
  - Metrics: SQL accuracy, RAG relevance (NDCG@5), end-to-end answer quality
  - RAG vs. context-stuffing comparison
- Results output to `tests/benchmarks/results/`

**QA:** Benchmark runner executes without errors, produces metrics report, establishes baseline numbers.

---

### [ ] Task 2.8 — Phase 2 Tests
**Agent:** Backend Architect  
**Description:** Test suite for all Phase 2 deliverables.  
**Deliverables:**
- `tests/unit/test_router.py` — Query classification tests (5 query types)
- `tests/unit/test_sql_flow.py` — SQL generation + validation tests
- `tests/unit/test_privacy.py` — PII scrubbing tests (incl. tool anonymization)
- `tests/unit/test_rag.py` — Ingestion + retrieval tests
- `tests/unit/test_tools.py` — Browser/search anonymization tests
- `tests/integration/test_graph.py` — Full LangGraph flow integration tests (incl. RESEARCH flow)

**QA:** `make test` → all tests pass including new Phase 2 tests.

---

## Phase 3: User-Facing MVP (Milestone 3)

> **Focus:** UI, market data, end-to-end integration.
> **Exit Criteria:** User opens Gradio UI → uploads CSV → asks questions → gets contextual financial advice → HITL review works.

### [ ] Task 3.1 — Market Data Adapters
**Agent:** Backend Architect  
**Description:** Real-time market data fetching with TTL caching.  
**Deliverables:**
- `src/aegis/market/bcra.py` — BCRA official rates adapter
- `src/aegis/market/mep_ccl.py` — MEP/CCL rates (ambito scraper + coingecko fallback)
- `src/aegis/market/yahoo.py` — Yahoo Finance adapter for USD assets
- `src/aegis/market/cache.py` — TTL-based in-memory + DB cache layer
- Rate storage in `exchange_rates` table

**QA:** Adapters fetch real data, cache respects TTL, fallback works when primary source fails.

---

### [ ] Task 3.2 — Gradio UI
**Agent:** Frontend Developer  
**Description:** Chat interface with file upload and HITL review.  
**Deliverables:**
- `src/aegis/ui/app.py`
  - Chat panel with conversation history
  - CSV file upload with parser integration
  - Staleness warning banner
  - HITL categorization review panel (flagged transactions table)
  - Settings panel (API key, cloud LLM selection, model config)
  - Status indicators (llama.cpp health, DB connection, data freshness)

**QA:** UI loads, chat works, file upload triggers parser, HITL panel shows flagged transactions, settings persist.

---

### [ ] Task 3.3 — Cloud LLM Integration
**Agent:** AI Engineer  
**Description:** Cloud LLM routing for HYBRID queries with graceful degradation.  
**Deliverables:**
- Cloud LLM client — provider-agnostic (OpenAI / Anthropic / Gemini / local fallback)
- Integration with Privacy Node output → Cloud LLM → Response reconstruction via redaction map
- Graceful degradation: when no API key or cloud disabled, route to local Qwen 3.5
- Token usage logging and cost tracking

**QA:** HYBRID query flows through: SQL → Privacy → Cloud → Reconstruct. No-API-key scenario falls back to local.

---

### [ ] Task 3.4 — End-to-End Integration
**Agent:** Backend Architect  
**Description:** Wire all components together and run through full user scenarios.  
**Deliverables:**
- Full pipeline test: CSV upload → parse → categorize → ask question → get answer
- All 5 query types tested end-to-end (incl. RESEARCH with anonymized tools)
- Cloud and local-only modes verified
- Error handling for all failure modes

**QA:** 5 user scenario scripts pass. Error modes handled gracefully. Performance within acceptable bounds.

---

### [ ] Task 3.5 — Documentation & README
**Agent:** Backend Architect  
**Description:** Public-facing documentation and contributor setup guide.  
**Deliverables:**
- `README.md` — Project overview, quickstart, architecture diagram, contributing
- `CONTRIBUTING.md` — Development setup, coding standards, PR process
- Inline docstrings on all public functions
- `make docs` target (optional — MkDocs or similar)

**QA:** New contributor can go from `git clone` to running the app in < 10 minutes following README.

---

### [ ] Task 3.6 — Phase 3 Tests & Final QA
**Agent:** Backend Architect  
**Description:** Full test suite coverage and final quality validation.  
**Deliverables:**
- `tests/unit/test_market.py` — Market adapter tests
- `tests/integration/test_end_to_end.py` — Full pipeline integration tests
- `tests/integration/test_ui.py` — Gradio UI interaction tests (if feasible)
- Coverage target: > 80% for core modules

**QA:** `make test` → all tests pass, coverage > 80%, no critical lint issues.

---

## Agent Assignment Summary

| Agent | Tasks |
|-------|-------|
| **Backend Architect** | 0.2, 1.1, 1.3, 1.4, 1.6, 2.6, 2.8, 3.1, 3.4, 3.5, 3.6 |
| **DevOps Automator** | 1.2 |
| **AI Engineer** | 0.1, 0.3, 0.4, 0.5, 1.5, 2.1, 2.2, 2.3, 2.3b, 2.4, 2.5, 2.7, 3.3 |
| **Frontend Developer** | 3.2 |

---

## Pipeline Orchestration Rules

1. **Task order within a phase is sequential** — each task depends on the previous
2. **QA validation after every task** — no task advances without passing QA
3. **Max 3 retry attempts per task** — escalate after 3 failures
4. **Phase gate** — all tasks in a phase must pass before advancing to the next phase
5. **Benchmarks (2.7) are evaluate-only** — they establish baselines, not pass/fail gates
