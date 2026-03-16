# Aegis Finance - Agent Guidelines

Welcome to the Aegis Finance repository. This file contains critical context, workflows, and conventions to follow when assisting with development in this codebase.

## 1. Project Overview
Aegis Finance is a privacy-first personal finance advisor powered by a hybrid local/cloud LLM architecture. It handles sensitive financial data (multi-currency: ARS, USD, USDT, EUR).
**Core Mandate:** Privacy is paramount. Zero Personally Identifiable Information (PII) should ever be logged or sent to external cloud APIs without passing through the local Privacy Middleware.

## 2. Build, Lint, and Test Commands

We use `poetry` for dependency management and environment isolation. All commands should generally be prefixed with `poetry run` to ensure they execute within the correct virtual environment.

### Setup
- **Install Dependencies:** `poetry install`
- **Setup SpaCy Models:** `make setup-models` or `poetry run python -m spacy download es_core_news_sm`
- **Start Database:** `docker compose up -d` (PostgreSQL 16 + pgvector)

### Linting & Formatting
We use `ruff` as our primary linter and formatter.
- **Check Linting:** `poetry run ruff check src/` (or `make lint`)
- **Format Code:** `poetry run ruff format src/`
- **Line Length:** 88 characters.

### Testing
We use `pytest` and `pytest-asyncio` for our testing framework.
- **Run All Tests:** `poetry run pytest tests/ -v` (or `make test`)
- **Run a Single Test File:** `poetry run pytest tests/path/to/test_file.py -v`
- **Run a Single Test Function:** `poetry run pytest tests/path/to/test_file.py::test_function_name -v`
- **Run Tests with a specific marker:** `poetry run pytest -m "not integration"`

*Tip:* When debugging a failing test, always run that single test function in isolation to save time and token context.

## 3. Code Style & Architecture Guidelines

### 3.1. Python Conventions & Typing
- **Target Version:** Python 3.11+. Use modern syntax (e.g., `list[str]` instead of `typing.List[str]`, `|` for Union types).
- **Type Hinting:** Comprehensive type hinting is mandatory for all function signatures (arguments and return types) and class attributes.
- **Docstrings:** Provide concise docstrings for all modules, public classes, and public functions explaining the *why* and *what*, but avoid redundant comments for obvious code.
- **Error Handling:** Use custom exception classes when appropriate. Catch specific exceptions rather than a broad `except Exception:` unless specifically building a top-level error boundary.
- **Naming Conventions:** 
  - `snake_case` for variables, functions, and modules.
  - `PascalCase` for classes and type variables.
  - `UPPER_SNAKE_CASE` for constants.

### 3.2. Imports and Structure
- All project source code lives under the `src/aegis/` directory.
- Use absolute imports referencing the base package (e.g., `from aegis.core.config import load_config` rather than `from ..config import load_config`).
- Group imports: Standard library first, third-party packages second, and internal `aegis` imports last.

### 3.3. Architectural Principles
- **SOLID Principles:** Keep classes and functions focused on a single responsibility.
- **Hybrid LLM Routing:** Respect the architectural boundary between Local LLMs (Qwen 3.5) and Cloud LLMs. 
  - Local LLMs handle: PII scrubbing, Text-to-SQL generation, RAG, and categorization.
  - Cloud LLMs handle: Complex reasoning and web search synthesis (only utilizing anonymized data).
- **LangGraph:** Orchestration logic and state machines should leverage LangGraph. Maintain clear state definitions.

### 3.4. Security & Privacy
- **No Hardcoded Secrets:** Never hardcode passwords, API keys, or tokens. Rely on environment variables or `config.yaml`.
- **PII Handling:** When writing or modifying logic that touches user data (transactions, names, balances), ensure it integrates with the existing Privacy Middleware before data leaves the local environment.
- **Database Safety:** Ensure Text-to-SQL functionality executes against restricted read-only views, preventing destructive operations.

## 4. Agent Operational Instructions
When operating autonomously in this repository, please:
1. Always run `poetry run ruff check <file>` after creating or heavily modifying a Python file.
2. If modifying core logic, immediately run the corresponding test file to verify you haven't broken existing functionality.
3. If creating a new feature, write a test for it in the `tests/` directory matching the module structure.
4. Assume the user is developing locally on Windows/Linux with Docker running. Always ensure paths are cross-platform compatible (`pathlib` preferred over raw string manipulation).