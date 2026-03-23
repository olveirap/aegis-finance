# Aegis Finance — Phased Task List
**Orchestrated by:** Agents Orchestrator
**Date:** 2026-03-07 | **Status:** Planning (v3 — Resolved architectural issues)

---

## Pipeline Overview

```
Phase 0: KB Curation ─┐
     (Weeks 1–3)      │──▶ Phase 2: Intelligence ──▶ Phase 3: MVP
Phase 1: Data Found. ─┘        (Weeks 4–7)           (Weeks 8–10)
     (Weeks 1–3)
                       ──▶ Milestone 4: SAT-Graph RAG + Drift (Post-MVP)
```

Phases 0 and 1 run **in parallel**. Phase 2 requires both to complete.
Milestone 4 (SAT-Graph RAG) starts after MVP.

Each phase follows the Orchestrator workflow:
`PM → Architecture → [Developer ↔ QA loop] → Integration`

### Phase 0 Dependency Chain

```
Task 0.1 (Ontology) ──────────────┐
                                   ├──▶ Task 0.2b (Source YAMLs)
Task 0.2 (Ingestion Framework) ───┘       │
                                           ▼
                                   Task 0.3 (Dedup/Quality)
                                           │
                                           ▼
                                   Task 0.4 (Embedding/Storage)
                                           │
                                           ▼
                                   Task 0.5 (RAG Benchmarks)
```

Tasks 0.1 and 0.2 run **in parallel**. Task 0.2b requires both to complete.

### Ingestion vs. Market Adapters

| Concern | Ingestion (Task 0.2) | Market Adapters (Task 3.1) |
|---------|---------------------|---------------------------|
| **When** | Batch/scheduled (cron) | Query-time (synchronous) |
| **Output** | `RawDocument` → embed → pgvector | Structured data → LangGraph state |
| **Purpose** | KB population for RAG | Live context injection for answers |
| **Shared** | `src/aegis/common/http_client.py` | Same shared HTTP client |

---

## Phase 0: Knowledge Base Data Gathering (Milestone 0, parallel to M1)

> **Focus:** Scrape, curate, and structure financial knowledge for RAG using a Connector/Extractor/Normalizer architecture.
> **Exit Criteria:** pgvector contains quality-gated, deduplicated, ontology-tagged embeddings from >= 5 source types, plus extracted entities/relations. RAG benchmarks pass.
> **Specialist Roles:** Data Engineers, RAG Specialists, Ontology Experts.

### [x] Task 0.1 — Ontology & Taxonomy Design
**Agent:** AI Engineer (Ontology Expert role)
**Description:** Define the topic taxonomy, entity relationships (for future Graph DB), and metadata schema for the knowledge base. Extends toward FIBO alignment.
**Deliverables:**
- `src/aegis/kb/ontology.py` — Topic taxonomy and Graph node/edge definitions
  - Personal Finance: budgeting, saving, emergency fund, debt management
  - Investing: stocks, bonds, CEDEARs, FCIs, ETFs, crypto
  - Argentine-specific: ganancias, bienes personales, MEP/CCL, inflación, plazo fijo
  - Regulations: AFIP, BCRA, CNV, UIF
  - Real Estate: mortgage, rental, property tax
  - FIBO-aligned `GraphNodeType`: `LEGAL_PERSON`, `SECURITY`, `DEBT_INSTRUMENT`, `ACCOUNT`, `CEDEAR`, `BOPREAL`, `BONO_CER`, `PLAZO_FIJO`, `CURRENCY_NODE`, `REGULATORY_EVENT`, `ACTION_NODE`
  - FIBO-aligned `GraphEdgeType`: `IS_ISSUED_BY`, `REPRESENTS`, `IS_HEDGED_BY`, `AMENDS`, `SUPERSEDES`, `TRIGGERS`, `HAS_CONVERSION_RATIO`, `VALID_DURING`
  - New `SourceType` entries: `API_TIMESERIES`, `RSS_FEED`, `VIDEO_WEBINAR`
- `src/aegis/kb/metadata.py` — Metadata schema for KB chunks (source, type, date, tags, language, relevance_score, temporal_validity, superseded_by, causal_chain)
- `src/aegis/kb/temporal.py` — `TemporalInterval`, `CausalActionNode`, `point_in_time_filter(t=now())`
- `src/aegis/kb/fibo_mapping.py` — FIBO IRI → internal node type mapping
- `data/knowledge/taxonomy.yaml` — YAML export of taxonomy for config/tooling

**QA:** Taxonomy covers all source categories. FIBO mapping validates. Temporal intervals logic is correct. Metadata schema validates against sample data.

---

### [x] Task 0.2 — Ingestion Framework (Connector/Extractor/Normalizer)
**Agent:** Backend Architect (Data Engineer role)
**Description:** Build the ingestion framework separating transport, extraction, and normalization. YAML-driven source registry. Produces `RawDocument`s for batch KB population — **not** real-time query-time data (see Task 3.1 for that).
**Deliverables:**

**Shared HTTP layer:**
- `src/aegis/common/http_client.py` — Thin `httpx.AsyncClient` wrapper with configurable retry + rate-limit. Used by both ingestion connectors and market adapters (Task 3.1) to avoid duplicating transport logic.

**Connectors** (`src/aegis/kb/ingestion/connectors/`):
- `base.py` — `BaseConnector(ABC)` with `async fetch(config, checkpoint) → RawBytes + SourceMeta`. Accepts `checkpoint: dict | None` for resume-on-crash.
- `http_polling.py` — Configurable GET/POST with throttles (covers BCRA, CNV, BYMA, blogs)
- `rest_api.py` — JSON/XML API clients (covers FRED, ECB, IOL **polling only**, DolarApi, INDEC). **Note:** IOL WebSocket streaming is deferred to Milestone 4 Task 4.4, where a `websocket.py` connector will be added.
- `rss_feed.py` — RSS/Atom feeds (covers SEC EDGAR RSS — stage 1 of multi-stage pipeline, see runner)
- `video.py` — `VideoConnector` (YouTube transcript API, cheap) + `WhisperVideoConnector` (expensive, separate class due to different cost/failure profiles)
- `reddit.py` — asyncpraw wrapper

**Extractors** (`src/aegis/kb/ingestion/extractors/`):
- `base.py` — `BaseExtractor(ABC)` with `extract(RawBytes) → ExtractedContent`. Supports chaining: extractors can be composed via `extractor: [pdf, llm_summarizer]` in source YAML.
- `html_extractor.py` — crawl4ai for rendered HTML → markdown. **Note:** crawl4ai requires Playwright/Chromium runtime — see Task 1.2 for Docker provisioning.
- `pdf_extractor.py` — Unstructured.io + LlamaParse fallback
- `timeseries_extractor.py` — Normalizes FRED/ECB/DolarApi/INDEC arrays to `(date, value, series_id)`
- `llm_summarizer.py` — Qwen 3.5 via llama.cpp: raw text → structured "Tips & Rules" summary. Used for book content (copyright-compliant summarization, never full text). Invoked as second stage in extractor chain.

**Pipeline orchestration & state:**
- `normalizer.py` — Any `ExtractedContent` → `RawDocument` with temporal_metadata + ontology tags
- `registry.py` — `SourceConfig` Pydantic model + YAML-driven source registry
- `runner.py` — **Multi-stage** pipeline orchestrator. Single-stage sources use flat `connector`/`extractor` fields. Multi-stage sources (e.g., SEC EDGAR: RSS → follow links → extract document) declare `stages` in YAML. Supports batch and incremental modes. Writes checkpoints per-source. On crash: resumes from last checkpoint.
- `state.py` — PostgreSQL `ingestion_state` table for incremental state persistence. Schema: `(source_name PK, last_run_at, last_seen_id, checkpoint JSONB, status TEXT)`
- `models.py` — `RawDocument` with `content_format`, `tables`, `temporal_metadata`, `raw_bytes_hash`

**QA:** Each connector type tested with mocked responses. Extractors tested with fixture files (including llm_summarizer with mocked LLM). Registry loads all YAML configs. Runner tested with multi-stage mock (RSS → follow → extract). Checkpoint resume tested with simulated crash. Full pipeline runs end-to-end for at least 1 source per connector type.

---

### [x] Task 0.2b — Source YAML Configurations
**Agent:** Backend Architect
**Depends on:** Task 0.1 (ontology tags) + Task 0.2 (framework)
**Description:** Define all source configurations as YAML files driving the ingestion framework. Uses `ontology_tags` and `jurisdiction` values from the ontology delivered in Task 0.1. Cannot be finalized until 0.1 completes.
**Deliverables:**
- `data/sources/global_regulatory.yaml` — SEC EDGAR (10-K, DEF 14A) using **multi-stage** config: `stages: [{connector: rss_feed, emit: document_urls}, {connector: http_polling, extractor: [pdf, html]}]`. FINRA Rulebooks.
- `data/sources/global_macro.yaml` — FRED (CPI, Fed Funds, GDP), ECB exchange rates
- `data/sources/argentina_regulatory.yaml` — BCRA Communications A/B/C, CNV Resolutions
- `data/sources/argentina_market.yaml` — IOL quotes (**polling only**, WebSocket deferred to M4), BYMA CEDEARs, DolarApi spreads
- `data/sources/argentina_macro.yaml` — INDEC IPC monthly reports
- `data/sources/blogs.yaml` — Finance blogs (AR/EN)
- `data/sources/reddit.yaml` — r/merval, r/personalfinance, r/argentina
- `data/sources/youtube.yaml` — CFA Argentina, Bloomberg Línea
- `data/sources/books.yaml` — Rapoport, Graham summaries. Uses `extractor: [pdf, llm_summarizer]` chain.

**QA:** All YAMLs load via registry. Auth env vars documented. Each source produces valid `SourceConfig`. Multi-stage SEC EDGAR config validates. Book configs use extractor chaining.

---

### [x] Task 0.3 — Deduplication & Quality Pipeline
**Agent:** AI Engineer (RAG Specialist role)
**Description:** Quality filtering, deduplication, and **lightweight heuristic** entity extraction.
**Deliverables:**
- `src/aegis/kb/pipeline.py` — End-to-end KB processing pipeline
  - Content hash deduplication (SHA-256)
  - Semantic deduplication (cosine similarity > 0.95 = duplicate)
  - Minimum length filter (< 50 tokens = discard)
  - Language detection (keep AR/ES and EN only)
  - Relevance scoring against ontology taxonomy
- `src/aegis/kb/chunker.py` — Configurable chunking (512 tokens, 64 overlap)
- `src/aegis/kb/tagger.py` — Automatic ontology tagging using Qwen 3.5 (via llama.cpp)
- `src/aegis/kb/extractor.py` — **Heuristic placeholder** for entity/relationship extraction: regex + spaCy NER for named entities (institutions, asset names, regulation IDs). Produces entity/relation candidates as chunk metadata — sufficient for pgvector-only retrieval with entity-filtered queries. **Replaced by DSPy triple extractor in Milestone 4 Task 4.2.** Heuristic output seeds the entity resolver's canonical name registry in 4.2.
- Source attribution preserved in every chunk's metadata

**QA:** Duplicate content is rejected. Low-quality content is filtered. Tags and extracted entities match expected ontology for test documents. Heuristic extractor identifies known entity names from sample BCRA/CNV documents.

---

### [x] Task 0.4 — KB Embedding & Storage
**Agent:** AI Engineer (RAG Specialist role)
**Description:** Embed curated chunks and store in pgvector.
**Deliverables:**
- `src/aegis/kb/embedder.py` — Batch embedding via Qwen3-embedding (llama.cpp)
  - Qwen3-VL-Embedding fallback for content with images/OCR
  - Batch processing with progress tracking
- Integration with `kb_chunks` table (DDL spec)
- `make kb-ingest` command to run full pipeline: ingest → process → embed → store
- Provenance tracking: every chunk links back to source URL/title

**QA:** ≥ 500 quality chunks stored in pgvector. Embedding dimensions = 1024. Similarity search returns relevant results for test queries.

---

### [x] Task 0.5 — RAG Knowledge Benchmarks
**Agent:** AI Engineer (RAG Specialist role)
**Description:** Benchmark suite to measure RAG quality over the curated KB.
**Deliverables:**
- [x] `tests/benchmarks/kb_quality.json` — 50+ question/answer pairs tailored to Argentine finance advisory scenarios
- [x] `tests/benchmarks/rag_benchmark.py` — Automated RAG quality benchmarks
  - Retrieval metrics: Recall@5, NDCG@5, MRR, LayerCoverage@5
  - Answer quality: human-eval format + blinded LLM-as-judge scoring (with strict hallucination detection)
  - RAG vs. context-stuffing comparison
- [x] Results output to `tests/benchmarks/results/kb_baseline.json` (Blocked pending local KB provisioning in Task 0.4)

**QA:** Benchmark runner completes without errors ([x] Dry-run validated). Baseline metrics established ([x] Pending).

---

## Phase 1: Data Foundation (Milestone 1)

> **Focus:** Database, Docker, parsers, synthetic data. No LLM integration yet.
> **Exit Criteria:** `docker-compose up` → populated DB → parser ingests a synthetic CSV → tests pass.

### [x] Task 1.1 — Project Scaffolding
**Agent:** Backend Architect
**Description:** Initialize Python project with `pyproject.toml`, directory structure per setup spec, `Makefile`, and `config.yaml` loader.
**Deliverables:**
- `pyproject.toml` with dependency groups (core, dev, test)
- `src/aegis/__init__.py` and all module `__init__.py` files
- `src/aegis/config.py` — YAML config loader with env var interpolation
- `config.yaml` — template with all sections
- `Makefile` — common commands (`make setup`, `make test`, `make lint`, `make db-up`)
- `.gitignore` with Python, IDE, and env file patterns

**QA:** `pip install -e ".[dev]"` succeeds, `make lint` passes, config loads without error. ✓ Completed 2026-03-11

---

### [x] Task 1.2 — Docker + PostgreSQL + pgvector
**Agent:** DevOps Automator
**Description:** Create `docker-compose.yml` and SQL init scripts for PostgreSQL with pgvector. Provision Playwright/Chromium for crawl4ai HTML extraction.
**Deliverables:**
- `docker-compose.yml` — pgvector/pgvector:pg16 service ✓
- `sql/001_schema.sql` — All base table DDLs from DDL spec (including `ingestion_state` table for Task 0.2 checkpoint persistence) ✓
- `sql/002_views.sql` — All curated view definitions ✓
- `src/aegis/db/connection.py` — Connection pool management with `psycopg` (pool) ✓
- `Dockerfile` — Includes `playwright install chromium` step (~400MB) for crawl4ai HTML extractor. **Alternative:** run crawl4ai on host only (outside Docker) and connect to Dockerized PostgreSQL — document both approaches.
- CI pipeline note: Playwright needs `--browser chromium` flag

**QA:** `docker-compose up -d` → `psql` connects → tables exist → `ingestion_state` table exists → views queryable → Playwright/Chromium available → `docker-compose down` clean. ✓ Completed 2026-03-11

---

### [x] Task 1.3 — Synthetic Data Generator
**Agent:** Backend Architect
**Description:** Python script to populate the sandbox with realistic Argentine financial data.
**Deliverables:**
- `data/synthetic/generate.py` — Faker + NumPy generator (~1,519 transactions generated) ✓
  - 3–5 accounts (checking ARS, savings USD, crypto wallet, brokerage) ✓
  - 6 months of transactions (200–400/month, realistic categories) ✓
  - Exchange rates with MEP/official spread simulation (758 rates) ✓
  - Sample assets (CEDEARs, ETFs, USDT) (5 assets) ✓
  - Income sources (salary, freelance) (2 sources) ✓
- `sql/003_seed_synthetic.sql` — Optional SQL-based alternative seed (2,330 LOC) ✓

**QA:** `python data/synthetic/generate.py` → `SELECT COUNT(*) FROM transactions` returns > 1000 rows → views return sensible aggregates. ✓ Completed 2026-03-11

---

### [x] Task 1.4 — Statement Parser Framework
**Agent:** Backend Architect
**Description:** Abstract parser interface and first concrete CSV parser.
**Deliverables:**
- `src/aegis/parsers/base.py` — `BaseParser` ABC with `parse(file_path) → list[Transaction]` (269 LOC) ✓
- `src/aegis/parsers/bank_csv.py` — Generic CSV parser with configurable column mapping (312 LOC, handles Argentine formats) ✓
- Duplicate detection via `(account_id, date, amount, merchant_raw)` constraint ✓
- Import batch tracking via `import_batches` table ✓

**QA:** Parser ingests a synthetic CSV, inserts rows, duplicate re-import is rejected, import batch is recorded. ✓ Completed 2026-03-11

---

### [x] Task 1.5 — Transaction Categorizer (Rule-Based Baseline)
**Agent:** AI Engineer
**Description:** Initial rule-based categorizer with keyword matching. LLM categorizer deferred to Phase 2.
**Deliverables:**
- `src/aegis/parsers/categorizer.py` — RuleBasedCategorizer implementation ✓
  - `RuleBasedCategorizer` — keyword-to-category mapping (e.g., "supermercado" → Food) ✓
  - Confidence scoring (1.0 for exact keyword match, 0.8 for partial) ✓
  - HITL flagging when `score < 0.85` or multi-label conflict ✓
  - `is_flagged = True` on ambiguous transactions ✓
- `data/category_rules.yaml` — keyword → category mapping file (14 categories, 100+ Argentine keywords) ✓

**QA:** Categorizer assigns correct categories to known merchants, flags ambiguous ones, confidence scores are in valid range. ✓ Completed 2026-03-11

---

### [x] Task 1.6 — Phase 1 Tests
**Agent:** Backend Architect
**Description:** Test suite for all Phase 1 deliverables.
**Deliverables:**
- `tests/unit/test_config.py` — Config loader tests (10 tests) ✓
- `tests/unit/test_parser.py` — CSV parser tests (31 tests, including Argentine format normalization) ✓
- `tests/unit/test_categorizer.py` — Categorizer tests (10 tests, HITL flagging validation) ✓
- `tests/integration/test_db.py` — Database connection and basic queries (5 tests) ✓
- `tests/integration/test_import_pipeline.py` — End-to-end: CSV → parse → categorize → DB insert (1 test) ✓

**QA:** `make test` → 129 unit tests pass (52 Phase 1 + 77 Phase 0), 0 failures, coverage report generated, all Phase 1 code passes `ruff check` lint. ✓ Completed 2026-03-11

---

## Phase 2: Intelligence Layer (Milestone 2)

> **Focus:** LangGraph, LLM integration, RAG, privacy, benchmarks.
> **Exit Criteria:** User can type a financial question → system routes, queries DB, retrieves knowledge, scrubs PII, and returns an answer.

### [x] Task 2.1 — LangGraph Orchestrator Setup
**Agent:** AI Engineer
**Description:** Create the main LangGraph state machine with router node.
**Deliverables:**
- `src/aegis/graph/__init__.py` — Graph builder and state definition
- `src/aegis/graph/router.py` — Router node with query type classification
  - Uses Qwen 3.5 via llama.cpp for classification
  - Output: `{ route, query_type, requires_cloud, requires_tools }`
- State schema: `AegisState` with query, history, sql_result, rag_chunks, privacy_output, tool_results

**QA:** Router correctly classifies 10+ test queries into 5 categories (incl. RESEARCH). Unit tests with mocked llama.cpp responses. ✓ Completed 2026-03-21

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

### [ ] Task 3.1 — Market Data Adapters (Real-Time Query-Time)
**Agent:** Backend Architect
**Description:** **Synchronous real-time** market data fetching with TTL caching for **query-time context injection** (e.g., "what's the MEP dollar right now?"). These are NOT duplicates of ingestion sources in Task 0.2 — ingestion populates the KB asynchronously; market adapters provide live data at query time for LangGraph state. Both use `src/aegis/common/http_client.py` (from Task 0.2) to avoid duplicating HTTP transport logic.
**Deliverables:**
- `src/aegis/market/bcra.py` — BCRA official rates adapter (uses shared HTTP client)
- `src/aegis/market/mep_ccl.py` — MEP/CCL rates (ambito scraper + coingecko fallback)
- `src/aegis/market/yahoo.py` — Yahoo Finance adapter for USD assets
- `src/aegis/market/cache.py` — TTL-based in-memory + DB cache layer
- Rate storage in `exchange_rates` table

**QA:** Adapters fetch real data, cache respects TTL, fallback works when primary source fails. Adapters use shared HTTP client, not their own `httpx` instances.

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

## Milestone 4: SAT-Graph RAG + Drift Handling (Post-MVP)

> **Focus:** Neo4j graph store, DSPy triple extraction, hybrid retrieval, streaming CDC, Bayesian uncertainty.
> **Exit Criteria:** System uses both pgvector and Neo4j for retrieval. Temporal versioning prevents stale advice. Drift scoring flags uncertain answers.

### [ ] Task 4.1 — Neo4j Graph Store
**Agent:** Data Engineer + DevOps
**Description:** Add Neo4j to Docker stack, build graph CRUD layer.
**Deliverables:**
- `docker-compose.yml` update with Neo4j Community service
- `src/aegis/kb/graph_store.py` — Neo4j driver, CRUD, temporal edges, Cypher builder

**QA:** Neo4j starts in Docker. Can create/read/update/delete nodes and edges. Temporal filtering works.

---

### [ ] Task 4.2 — DSPy Triple Extraction (Replaces Task 0.3 Heuristic)
**Agent:** AI Engineer
**Description:** **Replaces** the heuristic entity extractor from Task 0.3 with proper Subject-Predicate-Object triple extraction using DSPy + local Qwen 3.5. Seeds entity resolver with canonical names discovered by the 0.3 heuristic.
**Deliverables:**
- `src/aegis/kb/triple_extractor.py` — DSPy signatures, entity normalization, confidence scoring. Replaces `src/aegis/kb/extractor.py` from Task 0.3.
- `src/aegis/kb/entity_resolver.py` — Fuzzy matching + canonical name registry. Bootstrapped from 0.3 heuristic entity output.

**QA:** Extracts triples from sample BCRA/CNV documents. No duplicate entities for "BCRA" vs "Central Bank". Quality exceeds heuristic baseline from 0.3.

---

### [ ] Task 4.3 — Hybrid Retriever (Vector + Graph)
**Agent:** Semantic Search Researcher
**Description:** Fuse pgvector similarity and Neo4j multi-hop traversal.
**Deliverables:**
- `src/aegis/rag/hybrid_retriever.py` — Query routing, fusion scoring, temporal filtering
- Update `src/aegis/rag/retriever.py` to route through hybrid

**QA:** Multi-hop queries (e.g., CEDEAR → issuer → regulation) return correct paths. Temporal filter respects `t=now()`.

---

### [ ] Task 4.4 — Streaming CDC & Drift Handling
**Agent:** Backend Architect + Semantic Search Researcher
**Description:** Real-time updates, IOL WebSocket streaming (deferred from Task 0.2), and uncertainty scoring.
**Deliverables:**
- `src/aegis/kb/ingestion/streaming/cdc_connector.py` — PostgreSQL LISTEN/NOTIFY for price updates
- `src/aegis/kb/ingestion/connectors/websocket.py` — WebSocket streaming connector for IOL real-time price feeds (deferred from Phase 1 where IOL uses polling via `rest_api.py`)
- `src/aegis/kb/ingestion/streaming/freshness_tracker.py` — Per-source freshness monitoring
- `src/aegis/rag/uncertainty_scorer.py` — Bayesian embedding entropy + drift risk flagging

**QA:** CDC updates propagate within seconds. IOL WebSocket receives live price updates. High-entropy queries are flagged. Stale sources trigger alerts.

---

### [ ] Task 4.5 — Stress Test Suite
**Agent:** AI Engineer
**Description:** Complex user stories for multi-hop RAG validation.
**Deliverables:**
- `tests/benchmarks/stress_test_generator.py` — Argentine investor profiles with tax/portfolio/global triggers
- 10+ multi-hop scenarios validated against graph traversal

**QA:** All scenarios produce coherent multi-hop recommendations. Graph paths are auditable.

---

## Agent Assignment Summary

| Agent | Tasks |
|-------|-------|
| **Backend Architect** | 0.2, 0.2b, 1.1, 1.3, 1.4, 1.6, 2.6, 2.8, 3.1, 3.4, 3.5, 3.6, 4.4 |
| **DevOps Automator** | 1.2, 4.1 |
| **AI Engineer** | 0.1, 0.3, 0.4, 0.5, 1.5, 2.1, 2.2, 2.3, 2.3b, 2.4, 2.5, 2.7, 3.3, 4.2, 4.5 |
| **Data Engineer** | 0.2 (co-lead), 4.1 |
| **Semantic Search Researcher** | 4.3, 4.4 |
| **Frontend Developer** | 3.2 |

---

## Pipeline Orchestration Rules

1. **Task order within a phase is sequential** — each task depends on the previous
2. **QA validation after every task** — no task advances without passing QA
3. **Max 3 retry attempts per task** — escalate after 3 failures
4. **Phase gate** — all tasks in a phase must pass before advancing to the next phase
5. **Benchmarks (0.5, 2.7) are evaluate-only** — they establish baselines, not pass/fail gates
6. **Milestone 4 starts only after MVP** — Phases 0–3 must complete first
