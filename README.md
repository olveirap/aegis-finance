<h1 align="center">Aegis Finance</h1>

<p align="center">
  <strong>A privacy-first personal finance advisor powered by a hybrid local/cloud LLM architecture.</strong>
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-v0.5%20Draft-blue.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11+-blue.svg">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
</p>

## 🛡️ Introduction

Aegis Finance is designed for the **Sovereign Investor** — a privacy-conscious user managing multi-currency portfolios (ARS, USD, USDT, CEDEARs) who wants AI-assisted financial planning without surrendering their data to a third party.

The system ingests bank and credit card statements, builds a structured financial profile in PostgreSQL, and provides intelligent financial advice using local Retrieval-Augmented Generation (RAG) over curated knowledge. For complex market questions, it can optionally use cloud LLMs, fully sanitized of Personally Identifiable Information (PII) before any external API calls.

## ✨ Key Features

- **Privacy First:** Zero PII is sent in cloud or external tool calls. A robust two-pass Privacy Middleware scrubs all data locally before any external request, calculating a continuous risk score via Microsoft Presidio.
- **Hybrid LLM Architecture:** A LangGraph orchestrator dynamically routes your queries to a local LLM (Qwen 3.5 via `llama.cpp`) or provider-agnostic cloud LLMs (OpenAI, Anthropic, Gemini) depending on privacy constraints and query complexity.
- **Multilingual & Multi-Currency Native:** Seamlessly handles ARS, USD, USDT, and EUR with integrated USD-equivalent conversions throughout, tailored for users with diverse portfolios.
- **Local Text-to-SQL Flow:** Chat with your finances directly. Natural language questions are translated securely into valid queries against structured PostgreSQL views. 
- **Intelligent RAG:** Hybrid retrieval from a local `pgvector` knowledge base capturing financial laws, investment rules, and real-time market data (via BCRA, BYMA, and Yahoo Finance APIs).

## 🏗️ Architecture

Aegis handles information routing efficiently, separating local processing from required cloud analysis:

| Layer | Technology | Execution |
|-------|------------|-----------|
| **Local LLM** | Qwen 3.5 via `llama.cpp` | Local GPU (Text-to-SQL, PII scrub, RAG, categorization) |
| **Cloud LLM (Optional)** | Provider-agnostic (OpenAI/Anthropic/Gemini) | Cloud (Complex reasoning, web search synthesis) — *anonymized inputs only* |
| **Database** | PostgreSQL 16 + `pgvector` | Local Docker |
| **UI** | Gradio | Localhost |
| **Orchestrator** | LangGraph | Local state-machine graph for query routing |

## 🚀 Getting Started

### Prerequisites
- **Python 3.11+**
- **Docker** & **Docker Compose**
- **llama.cpp** (running locally with Qwen 3.5 and Qwen3-Embedding models)
- External API keys (Optional, configurable in `config.yaml`)

### Installation & Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/aegis-finance.git
   cd aegis-finance
   ```

2. **Set up the virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   pip install -e ".[dev]"
   ```

3. **Configure your environment**
   Copy the default configuration template and edit it as needed:
   ```bash
   cp config.yaml.example config.yaml
   ```
   *(Ensure your `AEGIS_DB_PASSWORD` and optional `AEGIS_CLOUD_API_KEY` are exported properly in your terminal.)*

4. **Initialize Database**
   This command starts PostgreSQL with `pgvector` and automatically runs the init SQL scripts:
   ```bash
   docker compose up -d
   ```

5. **Generate Synthetic Data (Optional)**
   Populate the database with realistic but synthetic Argentine financial data:
   ```bash
   python data/synthetic/generate.py
   ```

6. **Run the Application**
   ```bash
   python src/aegis/ui/app.py
   ```
   Open `http://127.0.0.1:7860` in your browser.

## 🗺️ Roadmap & Milestones

- **Milestone 0 & 1:** Knowledge Base Gathering, PostgreSQL schema setup, Docker environments, CLI parsers & Synthetic Data. *(Current Focus)*
- **Milestone 2 (Intelligence Layer):** LangGraph integration, Text-to-SQL pipeline, RAG embeddings, Privacy Middleware setup, SLM-based Categorization, Quality Benchmarks.
- **Milestone 3 (User-Facing MVP):** Real-time Market Data adapters, Gradio interface integration, HITL categorization, End-to-End interactions in UI.

For a more granular view, see [project-tasks/aegis-finance-tasklist.md](project-tasks/aegis-finance-tasklist.md).

## 🤝 Contributing

We welcome contributions and architectural feedback! Please ensure you:
1. Review the architecture guidelines in the `project-specs/` folder.
2. Verify you aren't committing any PII (keep data synthetic).
3. Follow SOLID principles.
4. Follow the project's coding standards.

Please see `CONTRIBUTING.md` (coming soon) for robust contribution guidelines.

## 📝 License

Distributed under the MIT License. See `LICENSE` for more information.
