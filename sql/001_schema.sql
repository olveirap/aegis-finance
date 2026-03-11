-- =============================================================================
-- Aegis Finance — Base Schema
-- File: sql/001_schema.sql
-- Description: All base table DDLs for the aegis_finance database.
-- Runs automatically on first container init via docker-entrypoint-initdb.d.
-- =============================================================================

-- ── Extensions ──────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS vector;

-- ── accounts ────────────────────────────────────────────────────────────────

CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,
    institution     VARCHAR(100),
    account_type    VARCHAR(20) NOT NULL
        CHECK (account_type IN ('checking', 'savings', 'credit_card', 'crypto_wallet', 'brokerage')),
    currency        VARCHAR(10) NOT NULL DEFAULT 'ARS'
        CHECK (currency IN ('ARS', 'USD', 'USDT', 'EUR')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

-- ── transactions ────────────────────────────────────────────────────────────

CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    date            DATE NOT NULL,
    amount          DECIMAL(18, 2) NOT NULL,
    currency        VARCHAR(10) NOT NULL DEFAULT 'ARS'
        CHECK (currency IN ('ARS', 'USD', 'USDT', 'EUR')),
    merchant_raw    TEXT,
    merchant_clean  VARCHAR(200),
    description     TEXT,
    category        VARCHAR(50),
    category_score  DECIMAL(3, 2),
    category_source VARCHAR(20) DEFAULT 'auto'
        CHECK (category_source IN ('auto', 'user', 'hitl')),
    is_flagged      BOOLEAN DEFAULT FALSE,
    import_batch_id UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (account_id, date, amount, merchant_raw)
);

CREATE INDEX idx_transactions_date      ON transactions(date DESC);
CREATE INDEX idx_transactions_category  ON transactions(category) WHERE category IS NOT NULL;
CREATE INDEX idx_transactions_flagged   ON transactions(is_flagged) WHERE is_flagged = TRUE;
CREATE INDEX idx_transactions_account   ON transactions(account_id);
CREATE INDEX idx_transactions_import    ON transactions(import_batch_id);

-- ── import_batches ──────────────────────────────────────────────────────────

CREATE TABLE import_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    file_name       VARCHAR(255) NOT NULL,
    file_hash       VARCHAR(64) NOT NULL,
    row_count       INTEGER NOT NULL,
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    parser_used     VARCHAR(50) NOT NULL,
    status          VARCHAR(20) DEFAULT 'completed'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

-- ── assets ──────────────────────────────────────────────────────────────────

CREATE TABLE assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    asset_type      VARCHAR(30) NOT NULL
        CHECK (asset_type IN ('cash', 'cedear', 'stock', 'etf', 'crypto', 'bond', 'fci')),
    ticker          VARCHAR(20),
    quantity        DECIMAL(18, 8) NOT NULL DEFAULT 0,
    avg_cost_usd    DECIMAL(18, 2),
    last_price_usd  DECIMAL(18, 4),
    last_price_at   TIMESTAMPTZ,
    currency        VARCHAR(10) NOT NULL DEFAULT 'USD',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assets_ticker  ON assets(ticker);
CREATE INDEX idx_assets_type    ON assets(asset_type);
CREATE INDEX idx_assets_account ON assets(account_id);

-- ── income_sources ──────────────────────────────────────────────────────────

CREATE TABLE income_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label           VARCHAR(100) NOT NULL,
    type            VARCHAR(30) NOT NULL
        CHECK (type IN ('salary', 'freelance', 'investment', 'rental', 'government', 'other')),
    currency        VARCHAR(10) NOT NULL DEFAULT 'ARS',
    monthly_amount  DECIMAL(18, 2),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── exchange_rates ──────────────────────────────────────────────────────────

CREATE TABLE exchange_rates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rate_type       VARCHAR(20) NOT NULL
        CHECK (rate_type IN ('official', 'mep', 'ccl', 'blue', 'crypto')),
    base_currency   VARCHAR(10) NOT NULL DEFAULT 'USD',
    quote_currency  VARCHAR(10) NOT NULL DEFAULT 'ARS',
    buy_rate        DECIMAL(12, 4),
    sell_rate       DECIMAL(12, 4),
    mid_rate        DECIMAL(12, 4) NOT NULL,
    source          VARCHAR(50),
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_exchange_rates_type ON exchange_rates(rate_type, fetched_at DESC);

-- ── kb_chunks (RAG knowledge base) ─────────────────────────────────────────

CREATE TABLE kb_chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content             TEXT NOT NULL,
    embedding           vector(1024),
    source              VARCHAR(500),
    source_title        VARCHAR(300),
    source_type         VARCHAR(30)
        CHECK (source_type IN (
            'blog', 'reddit', 'youtube', 'regulation', 'book_summary',
            'user_note', 'api_timeseries', 'rss_feed', 'video_webinar'
        )),
    topic_tags          TEXT[],
    argentina_specific  BOOLEAN DEFAULT FALSE,
    chunk_index         INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_kb_chunks_embedding
    ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_kb_chunks_tags
    ON kb_chunks USING gin(topic_tags);
CREATE INDEX idx_kb_chunks_argentina
    ON kb_chunks(argentina_specific) WHERE argentina_specific = TRUE;

-- ── kb_entities (graph database preparation) ────────────────────────────────

CREATE TABLE kb_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, entity_type)
);

CREATE INDEX idx_kb_entities_name ON kb_entities(name);
CREATE INDEX idx_kb_entities_type ON kb_entities(entity_type);

-- ── kb_relations (graph database preparation) ───────────────────────────────

CREATE TABLE kb_relations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    head_entity_id  UUID NOT NULL REFERENCES kb_entities(id) ON DELETE CASCADE,
    tail_entity_id  UUID NOT NULL REFERENCES kb_entities(id) ON DELETE CASCADE,
    relation_type   VARCHAR(100) NOT NULL,
    chunk_id        UUID REFERENCES kb_chunks(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(head_entity_id, tail_entity_id, relation_type)
);

CREATE INDEX idx_kb_relations_head ON kb_relations(head_entity_id);
CREATE INDEX idx_kb_relations_tail ON kb_relations(tail_entity_id);

-- ── ingestion_state (Phase 0 checkpoint persistence) ────────────────────────

CREATE TABLE ingestion_state (
    source_name     TEXT PRIMARY KEY,
    last_run_at     TIMESTAMPTZ,
    last_seen_id    TEXT,
    checkpoint      JSONB DEFAULT '{}',
    status          TEXT DEFAULT 'idle'
        CHECK (status IN ('idle', 'running', 'failed', 'completed'))
);
