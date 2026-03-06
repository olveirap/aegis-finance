# Aegis Finance — Project Setup Specification
**Version:** 0.5 | **Status:** Draft | **Date:** 2026-03-06

---

## 1. Product Vision

Aegis Finance is a **privacy-first personal finance advisor** powered by a hybrid local/cloud LLM architecture. It ingests bank and credit card statements, builds a structured financial profile in PostgreSQL, and provides intelligent financial advice using local RAG over curated knowledge and optional cloud LLM reasoning for complex market questions.

**Target persona:** The "Sovereign Investor" — a privacy-conscious user (initially in Argentina) managing multi-currency portfolios (ARS, USD, USDT, CEDEARs) who wants AI-assisted financial planning without surrendering their data to a third party.

---

## 2. Architecture Summary

```
User ──▶ Gradio UI ──▶ LangGraph Orchestrator
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         SQL Flow      RAG Flow     Privacy Node
              │             │             │
              ▼             ▼             ▼
         Local LLM     pgvector      Cloud LLM
       (Qwen 3.5)     (Local KB)   (Provider-agnostic)
              │                       ▲
              └──── PostgreSQL ───────┘
                  (anonymized only)
```

| Layer | What Runs | Where |
|-------|-----------|-------|
| **Local** | Qwen 3.5 (llama.cpp), PostgreSQL + pgvector, Presidio PII scanner, Gradio UI | User's machine (GPU) |
| **Cloud** | Any supported provider: OpenAI, Anthropic, Google Gemini, or local fallback | External — anonymized inputs only |
| **External APIs** | BCRA, BYMA/BCBA, Yahoo Finance, ambito.com (rates), web search | Public — no PII transmitted |

---

## 3. Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.11+ | Single language for all components |
| Orchestrator | LangGraph | State-machine graph for query routing |
| Local LLM | Qwen 3.5 via llama.cpp | Text-to-SQL, PII scrub, RAG synthesis, categorization |
| Cloud LLM | Provider-agnostic (OpenAI / Anthropic / Gemini / local fallback) | Complex market reasoning, web search synthesis |
| Database | PostgreSQL 16 + pgvector | Dockerized, local only |
| Embeddings | Qwen3-embedding via llama.cpp (Qwen3-VL-Embedding for OCR fallback) | Local GPU, multilingual support |
| Database access | Raw SQL with `psycopg` | No ORM — system generates SQL dynamically |
| PII Detection | Microsoft Presidio Analyzer | Local, post-regex pass validation |
| UI | Gradio | localhost-only, no auth needed for MVP |
| Containerization | Docker Compose | PostgreSQL + pgvector service |
| Testing | pytest + pytest-asyncio | Unit, integration, benchmark suites |
| Config | YAML (`config.yaml`) | LLM selection, privacy thresholds, API keys |

---

## 4. Repository Structure (Target)

```
aegis-finance/
├── aegis-finance-architecture.md     # Existing architecture doc (v0.2)
├── project-specs/                    # This directory
│   ├── aegis-finance-setup.md        # This file
│   ├── aegis-finance-ddl.md          # Database schema specification
│   └── aegis-finance-kb-pipeline.md  # Knowledge base ingestion spec (Milestone 2)
├── project-tasks/
│   └── aegis-finance-tasklist.md     # Phased task list with agent assignments
├── src/
│   └── aegis/
│       ├── __init__.py
│       ├── config.py                 # YAML config loader
│       ├── graph/                    # LangGraph orchestrator
│       │   ├── __init__.py
│       │   ├── router.py             # Router Node
│       │   ├── sql_flow.py           # Text-to-SQL Flow
│       │   ├── rag_flow.py           # RAG Retrieval Flow
│       │   ├── privacy.py            # Privacy Middleware Node
│       │   └── staleness.py          # Staleness Guardrail
│       ├── db/                       # Database layer
│       │   ├── __init__.py
│       │   ├── connection.py         # Connection pool management (psycopg)
│       │   └── views.py              # Curated SQL view definitions
│       ├── parsers/                   # Statement parsers
│       │   ├── __init__.py
│       │   ├── base.py               # Abstract parser interface
│       │   ├── bank_csv.py           # Generic bank CSV parser
│       │   ├── credit_card.py        # Credit card statement parser
│       │   └── categorizer.py        # ML category classifier
│       ├── privacy/                   # PII handling
│       │   ├── __init__.py
│       │   ├── regex_scrubber.py     # Pass 1: deterministic regex
│       │   ├── semantic_scrubber.py  # Pass 2: LLM semantic scrub
│       │   ├── redaction_map.py      # Local redaction map storage
│       │   └── risk_scorer.py        # Presidio-based risk scoring
│       ├── rag/                       # RAG pipeline
│       │   ├── __init__.py
│       │   ├── ingestion.py          # Document chunking + embedding
│       │   ├── retriever.py          # pgvector similarity search
│       │   └── reranker.py           # Cross-encoder reranking
│       ├── market/                    # Market data adapters
│       │   ├── __init__.py
│       │   ├── bcra.py               # BCRA official rates
│       │   ├── mep_ccl.py            # MEP/CCL dollar rates
│       │   ├── yahoo.py              # Yahoo Finance for USD assets
│       │   └── cache.py              # TTL-based market data cache
│       ├── tools/                     # Agent tools (browser, search)
│       │   ├── __init__.py
│       │   ├── web_search.py         # Anonymized web search tool
│       │   └── browser.py            # Anonymized browser tool
│       └── ui/                        # Gradio frontend
│           ├── __init__.py
│           └── app.py                # Gradio application
├── data/
│   ├── synthetic/                    # Faker-generated test data
│   │   └── generate.py              # Synthetic data generator
│   └── knowledge/                    # Curated KB documents (non-private)
├── sql/
│   ├── 001_schema.sql               # Base DDL
│   ├── 002_views.sql                # Curated semantic views
│   └── 003_seed_synthetic.sql       # Synthetic data seed
├── tests/
│   ├── unit/                         # Unit tests
│   ├── integration/                  # Integration tests (needs Docker)
│   └── benchmarks/                   # LLM quality benchmarks
│       ├── qa_finance.json           # Finance QA golden dataset
│       └── benchmark_runner.py       # Automated benchmark execution
├── docker-compose.yml                # PostgreSQL + pgvector
├── config.yaml                       # Runtime configuration
├── pyproject.toml                    # Python project definition
├── Makefile                          # Common commands
└── README.md                         # Public-facing docs
```

---

## 5. Core Modules — Functional Specification

### 5.1 Statement Parser (`src/aegis/parsers/`)

**Purpose:** Ingest bank/credit card CSV/PDF statements into the `transactions` table.

**Inputs:** CSV files (initially), PDF (future milestone) from Argentine banks (e.g., Santander, BBVA, Galicia).

**Outputs:** Structured rows in `transactions` table with `category`, `currency`, `amount`, `merchant`, `date`.

**Key Logic:**
- Abstract `BaseParser` interface with `parse(file_path) → list[Transaction]`
- Bank-specific CSV column mapping via config
- Multi-currency handling: ARS, USD, USDT with explicit `currency` column
- Duplicate detection via `(date, amount, merchant_raw)` composite key

### 5.2 Transaction Categorizer (`src/aegis/parsers/categorizer.py`)

**Purpose:** Multi-label classification of transactions with confidence scoring.

**Logic:**
1. Local SLM assigns categories with confidence scores per transaction
2. If `score < 0.85` or multi-label conflict → flag for HITL (Human-In-The-Loop) clarification
3. User corrections feed back into a local correction log for few-shot learning

**Categories (initial set):** Housing, Food, Transportation, Entertainment, Health, Education, Utilities, Subscriptions, Work-Expense, Savings, Investment, Transfer, Income, Other.

### 5.3 Privacy Middleware (`src/aegis/privacy/`)

**Purpose:** Two-pass PII scrubbing before any data reaches the cloud LLM **or any external tool (browser, web search)**.

**Pass 1 (Regex):** Deterministic pattern matching for CUIT, CBU, exact monetary values, emails, names. Monetary values replaced with range buckets, not `[REDACTED]`.

**Pass 2 (Semantic):** Qwen 3.5 audits the regex output for indirect identifiers (location hints, relative amounts, named entities).

**Scope:** The privacy middleware applies to:
- Cloud LLM prompts (HYBRID queries)
- **Browser tool queries** — when the agent uses a browser to research financial products
- **Web search queries** — when the agent searches for real-world pricing, returns, or alternatives

**Redaction Map:** Session-scoped SQLite table mapping redaction tokens to real values. Used to reconstruct concrete values in the user-facing response.

**Risk Score:** Presidio residual PII count / total tokens. If `> 0.05`, block cloud call and external tool usage.

### 5.4 Text-to-SQL Flow (`src/aegis/graph/sql_flow.py`)

**Purpose:** Convert natural language queries to SQL against curated views only.

**Guardrails:**
- Prompt injects only relevant view DDLs (selected via pgvector similarity on view descriptions)
- Read-only enforcement via prompt + SQL parser validation (no INSERT/UPDATE/DELETE/DROP)
- 4-step validation: syntax → schema → dry run (EXPLAIN) → sanity check
- Max 3 retries with structured error feedback to the model
- Currency mixing warning (ARS + USD aggregation without conversion)

### 5.5 RAG Retrieval (`src/aegis/rag/`)

**Purpose:** Hybrid retrieval from local knowledge base and market APIs.

**KB Ingestion Pipeline (offline):**
- Source documents (PDF, HTML, blog posts, summarized book rules)
- Chunking: 512 tokens with 64-token overlap
- Embedding via llama.cpp embed endpoint → pgvector storage with metadata

**Query-time Retrieval:**
1. Embed query locally
2. pgvector similarity search (k=5, optional `argentina_specific` filter)
3. Market data staleness check (prices: 15 min TTL, rates: 1 hr TTL)
4. Cross-encoder reranking of combined chunks

### 5.6 Market Data Adapters (`src/aegis/market/`)

**Purpose:** Real-time financial data for Argentine and USD markets.

| Adapter | Source | Data | TTL |
|---------|--------|------|-----|
| `bcra.py` | BCRA API | Official USD/ARS rate, monetary policy rates | 1 hour |
| `mep_ccl.py` | ambito.com (scrape) or pycoingecko (USDT proxy) | MEP/CCL dollar, blue dollar | 15 min |
| `yahoo.py` | Yahoo Finance API | US stock prices, ETF NAVs | 15 min |

> **Open Decision:** MEP/CCL data source. BYMA has no free API. Options: (a) scrape ambito.com, (b) USDT/ARS as CCL proxy via pycoingecko, (c) manual entry. Recommend (a) + (b) as fallback.

### 5.7 LangGraph Orchestrator (`src/aegis/graph/`)

**Purpose:** State-machine routing of user queries through the correct flow.

**Query Types:**
| Type | Flow | Cloud? | External? |
|------|------|--------|----------|
| `PERSONAL_FINANCIAL` | SQL Flow + optional RAG | No | No |
| `MARKET_KNOWLEDGE` | RAG (local KB first, then market API if stale) | No | Market APIs |
| `HYBRID` | SQL Flow → Privacy Node → Cloud LLM | Yes | No |
| `GENERAL_FINANCE` | Local RAG only | No | No |
| `RESEARCH` | Privacy Node → Web Search / Browser → Synthesis | Optional | Yes |

**`RESEARCH` flow:** When the user asks about real-world financial products, alternatives, or current pricing (e.g., "compare savings accounts from Galicia vs. BBVA"), the agent uses browser or search tools. **The query is anonymized through the Privacy Node before any external search**, ensuring no personal financial context leaks into search queries.

**Staleness Guardrail:** If `last_transaction_import > 30 days`, inject warning banner in UI and append disclaimer to SQL-based answers. Does not block queries.

### 5.8 Gradio UI (`src/aegis/ui/app.py`)

**Purpose:** Chat interface for financial Q&A.

**Features (MVP):**
- Chat panel with conversation history
- File upload for statement import (CSV)
- Staleness warning banner
- HITL categorization review panel (flagged transactions)
- Settings panel: API key config, cloud LLM selection
- No authentication required (localhost only)

### 5.9 Knowledge Base Data Gathering (`src/aegis/kb/`)

**Purpose:** Scrape, curate, and structure financial knowledge from multiple sources for RAG ingestion.

**Source Categories:**

| Source Type | Examples | Pipeline |
|-------------|----------|----------|
| **Books** | Personal finance, investing, Argentine tax guides | Summarize into structured "Tips & Rules" (no full text, avoid copyright) |
| **Blog posts** | Finance blogs (AR/EN), BCRA publications | HTML scraper → text extraction → chunking |
| **Reddit posts** | r/merval, r/personalfinance, r/argentina | Reddit API / PRAW → thread extraction → deduplication |
| **YouTube** | Finance channels (AR/EN) | Whisper transcription → text chunking |
| **Regulations** | AFIP, BCRA, CNV normativas | Official PDF/HTML → structured extraction |

**Pipeline:**
```
Source → Scraper (per-source adapter) → Raw Text Store
  → Deduplication & Quality Filter
  → Ontology Tagging (topic taxonomy)
  → Chunking (512 tokens, 64 overlap)
  → Qwen3-embedding (via llama.cpp)
  → pgvector storage with metadata
```

**Ontology Taxonomy (initial):**
- Personal Finance: budgeting, saving, emergency fund, debt management
- Investing: stocks, bonds, CEDEARs, FCIs, ETFs, crypto
- Argentine-specific: impuesto a las ganancias, bienes personales, MEP/CCL, inflación, plazo fijo
- Regulations: AFIP, BCRA, CNV, UIF
- Real Estate: mortgage, rental, property tax

**Quality Gates:**
- Minimum chunk relevance score vs. topic taxonomy
- Deduplication by content hash + semantic similarity (> 0.95 = duplicate)
- Source attribution preserved in metadata for provenance tracking
- Book content is summarized, never stored verbatim (copyright compliance)

---

## 6. Configuration (`config.yaml`)

```yaml
llm:
  local:
    model: "qwen3.5"                        # Qwen 3.5 via llama.cpp — multilingual
    llama_cpp_server: "http://localhost:8080"  # llama-server endpoint
  cloud:
    provider: "openai"                       # "openai" | "anthropic" | "gemini" | "local"
    api_key: "${AEGIS_CLOUD_API_KEY}"        # env var reference
    enabled: true                            # false → local-only mode (graceful degradation)
    # Model selection is provider-dependent, not configured here.
    # The system uses the provider's default/latest model.

embedding:
  model: "qwen3-embedding"                   # Primary: Qwen3-embedding (multilingual)
  ocr_fallback: "qwen3-vl-embedding"         # Fallback: Qwen3-VL-Embedding for OCR parsing
  dimension: 1024                            # Embedding vector dimension

privacy:
  risk_threshold: 0.05
  anonymize_tools: true                      # Also anonymize browser/search tool queries
  redaction_buckets:
    ars: [0, 50000, 500000, 5000000, 50000000]
    usd: [0, 100, 1000, 10000, 100000]

database:
  host: "localhost"
  port: 5432
  name: "aegis_finance"
  user: "aegis"
  password: "${AEGIS_DB_PASSWORD}"

market:
  cache_ttl:
    prices: 900     # 15 minutes
    rates: 3600     # 1 hour
  mep_source: "ambito"  # or "coingecko"

rag:
  chunk_size: 512
  chunk_overlap: 64
  top_k: 5

staleness:
  warn_after_days: 30
```

---

## 7. Resolved Design Decisions

| # | Decision | Resolution |
|---|----------|------------|
| 1 | **Local LLM** | Qwen 3.5 via llama.cpp — multilingual support critical for AR/EN content |
| 2 | **Embedding model** | Qwen3-embedding (primary) + Qwen3-VL-Embedding (OCR fallback) |
| 3 | **Cloud LLM** | Provider-agnostic: OpenAI, Anthropic, Gemini, or local fallback. No model pinning. |
| 4 | **ORM vs raw SQL** | Raw SQL with `psycopg` — system generates SQL dynamically |
| 5 | **No cloud API key** | Graceful degradation — log warning, route all queries to local flows |
| 6 | **Tool anonymization** | Browser/search tool queries pass through Privacy Node before execution |
| 7 | **Redaction map persistence** | Session-scoped (SQLite, ephemeral); encryption deferred to Milestone 3 |
| 8 | **MEP/CCL data** | Ambito scraper primary + coingecko USDT proxy fallback |
| 9 | **RAG vs. context stuffing** | Build both — benchmark to quantify cost/quality tradeoff |
| 10 | **PDF parsing** | Deferred to Milestone 2 — CSV is sufficient for MVP |

---

## 8. Privacy & Security Requirements

- **Zero PII in cloud calls**: Enforced by Privacy Middleware with measurable risk score
- **Zero PII in external tool calls**: Browser and web search queries are anonymized through the same Privacy Node
- **Zero private data in repo**: All test data is synthetic (Faker-generated)
- **Local-only database**: PostgreSQL runs in Docker on localhost, no external exposure
- **API keys via env vars**: Never committed to repo, loaded from `config.yaml` env references
- **Redaction map**: Stored in local SQLite, session-scoped, never persisted to disk by default

---

## 9. Milestones

### Milestone 0 — Knowledge Base Curation (Weeks 1–3, parallel to M1)
Scrape and curate personal finance knowledge from books, blogs, Reddit, YouTube, and Argentine regulations. Build ontology taxonomy. Produce embeddings for RAG benchmarking.

### Milestone 1 — Data Foundation (Weeks 1–3)
PostgreSQL schema, Docker setup, synthetic data generator, CSV statement parser, basic categorizer.

### Milestone 2 — Intelligence Layer (Weeks 4–7)
LangGraph orchestrator, Text-to-SQL flow, RAG pipeline, KB ingestion, privacy middleware, benchmarks.

### Milestone 3 — User-Facing MVP (Weeks 8–10)
Gradio UI, market data adapters, staleness guardrail, HITL categorization review, end-to-end integration testing.
