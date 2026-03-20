# Aegis Finance - Project Context & Instructions

Aegis Finance is a privacy-first personal finance advisor designed for the "Sovereign Investor." It uses a hybrid local/cloud LLM architecture to provide intelligent financial planning while strictly protecting user data.

## Project Overview

- **Purpose:** Securely ingest financial data, build a structured profile in PostgreSQL, and provide AI-assisted advice via a LangGraph orchestrator.
- **Core Mandate:** **Privacy First.** Zero Personally Identifiable Information (PII) is sent to external APIs. All data is scrubbed locally via a two-pass Privacy Middleware (Regex + Qwen 3.5 semantic scrub) before any cloud LLM interaction.
- **Architecture:**
    - **Local Layer:** Qwen 3.5 (via `llama.cpp`) handles Text-to-SQL, PII scrubbing, categorization, and RAG synthesis.
    - **Cloud Layer:** Provider-agnostic LLMs (OpenAI, Anthropic, Gemini) handle complex reasoning on anonymized data.
    - **Database:** PostgreSQL 16 + `pgvector` running in Docker.
    - **Orchestrator:** LangGraph state machine routing queries through specialized nodes.
- **Key Features:** Multi-currency support (ARS, USD, USDT, EUR), natural language Text-to-SQL against read-only views, and local RAG with Argentine-specific market data adapters.

## Tech Stack

- **Language:** Python 3.11+
- **Dependency Management:** Poetry
- **Orchestration:** LangGraph
- **Local LLM/Embeddings:** `llama.cpp` (Qwen 3.5 and Qwen3-embedding)
- **Database:** PostgreSQL + `pgvector` (Docker)
- **PII Detection:** Microsoft Presidio + Custom Regex
- **UI:** Gradio
- **Linting/Formatting:** Ruff (Line length: 88)
- **Testing:** Pytest + Pytest-asyncio

## Building and Running

### Setup
- **Install Dependencies:** `make setup` (or `poetry install`)
- **Download Models:** `make setup-models` (downloads spaCy `es_core_news_sm`)
- **Start Database:** `make db-up` (starts PostgreSQL + `pgvector` via Docker)

### Development Workflow
- **Run Tests:** `make test` (or `poetry run pytest tests/ -v`)
- **Linting:** `make lint` (or `poetry run ruff check src/`)
- **Formatting:** `poetry run ruff format src/`
- **Database Reset:** `make db-reset` (recreates the DB container)
- **Seed Data:** `make seed` (populates the DB with synthetic financial data)
- **KB Ingestion:** `make kb-ingest` (ingests sources from `data/sources` into `pgvector`)

### Running the App
- **Start UI:** `python src/aegis/ui/app.py`
- **Synthetic Data Generation:** `python data/synthetic/generate.py`

## Development Conventions

- **Surgical Changes:** Adhere to established patterns in `src/aegis/`. Use absolute imports (e.g., `from aegis.db.connection import ...`).
- **Privacy Enforcement:** Never bypass the `Privacy Middleware`. Ensure all user data is scrubbed before leaving the local environment.
- **Type Safety:** Mandatory type hinting for all function signatures and class attributes.
- **Text-to-SQL:** Always query against restricted read-only SQL views (`v_*`) defined in `sql/002_views.sql` rather than base tables.
- **Cross-Platform:** Use `pathlib` for file paths to ensure compatibility across Windows and Linux.
- **Testing:** New features or bug fixes must include tests in `tests/`. Reproduce bugs with a test case before fixing.
- **Git Flow:** Use Gitflow and worktrees for modifications. Never stage/commit changes unless explicitly asked.
- **Secrets:** Never hardcode secrets. Use `.env` or `config.yaml` with environment variable references.

## Key Directories

- `src/aegis/`: Core application logic (kb, db, parsers, privacy, graph).
- `data/`: Knowledge base sources, taxonomy, and synthetic data generation scripts.
- `sql/`: DDL for schema, views, and seed data.
- `project-specs/`: Detailed architecture, DDL, and setup specifications.
- `project-tasks/`: Task tracking and roadmap.
- `tests/`: Unit, integration, and quality benchmarks.
