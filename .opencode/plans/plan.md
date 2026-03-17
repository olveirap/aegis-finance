# Plan for Initializing Knowledge Base and Scraping

Based on the project's documentation (`project-tasks/aegis-finance-tasklist.md`, `Makefile`, and source code), here is the step-by-step plan to initialize the knowledge base and run the scraping pipeline locally.

## Prerequisites & Environment Setup

Before running the commands, you need to configure your environment variables. Although the codebase falls back to some defaults, setting up an explicit `.env` file ensures everything works smoothly, especially the database and any external API connectors (like Reddit).

1. **Create a `.env` file in the project root** and populate it with the necessary variables. For example:
   ```env
   # Database Configuration (matches defaults in code)
   AEGIS_DB_PASSWORD=aegis_dev
   AEGIS_DB_USER=aegis
   AEGIS_DB_NAME=aegis_finance
   AEGIS_DB_URL=postgresql://aegis:aegis_dev@localhost:5432/aegis_finance

   # Optional: External API Connectors (for scrapers if active in your data sources)
   # REDDIT_CLIENT_ID=your_client_id
   # REDDIT_CLIENT_SECRET=your_client_secret
   # REDDIT_USER_AGENT=AegisFinance/1.0
   ```

## Execution Steps

The project contains a `Makefile` that simplifies the execution process. Once your environment is configured, the following steps will be executed:

1. **Install Project Dependencies**
   Run the setup target to install all python dependencies using Poetry.
   ```bash
   make setup
   # Equivalent to: poetry install
   ```

2. **Download Required NLP Models**
   The project uses SpaCy for natural language processing, which requires downloading specific models (e.g., `es_core_news_sm`).
   ```bash
   make setup-models
   # Equivalent to: poetry run python -m spacy download es_core_news_sm
   ```

3. **Start the Database Infrastructure**
   Initialize the PostgreSQL database (with `pgvector`) in a Docker container in the background.
   ```bash
   make db-up
   # Equivalent to: docker compose up -d
   ```

4. **Run the Knowledge Base Ingestion Pipeline**
   This command starts the scraping/ingestion process from the sources defined in `data/sources/` (e.g., books, Argentina economy data, global news), processes them, embeds them, and stores them in the database.
   ```bash
   make kb-ingest
   # Equivalent to: poetry run python -m aegis.kb.cli ingest --sources data/sources
   ```

## Next Actions
If you approve this plan, I can proceed with creating the `.env` file for you and running these commands in sequence. Let me know if you need to add specific API keys to the environment or if default database credentials are fine!