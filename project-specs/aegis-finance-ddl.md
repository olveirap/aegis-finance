# Aegis Finance — Database DDL Specification
**Version:** 0.1 | **Milestone:** 1 | **Status:** Draft

---

## Design Principles

1. **Multi-currency native**: Every monetary column has a sibling `currency` column
2. **USD-equivalent everywhere**: All views expose a `_usd_equiv` aggregated column for cross-currency comparison
3. **Soft deletes**: `deleted_at` on user-facing tables, hard delete on ephemeral data (redaction maps)
4. **pgvector enabled**: `vector(1536)` columns for RAG embeddings (dimension matches `nomic-embed-text`)
5. **No PII in views sent to cloud**: Views marked "Sensitive" are never exposed to external LLMs

---

## Base Tables

### `accounts`
```sql
CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,          -- "Santander ARS", "Binance USDT"
    institution     VARCHAR(100),                   -- "Banco Santander", "Binance"
    account_type    VARCHAR(20) NOT NULL             -- 'checking', 'savings', 'credit_card', 'crypto_wallet', 'brokerage'
        CHECK (account_type IN ('checking', 'savings', 'credit_card', 'crypto_wallet', 'brokerage')),
    currency        VARCHAR(10) NOT NULL DEFAULT 'ARS'
        CHECK (currency IN ('ARS', 'USD', 'USDT', 'EUR')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
```

### `transactions`
```sql
CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    date            DATE NOT NULL,
    amount          DECIMAL(18, 2) NOT NULL,        -- Negative = expense, Positive = income/deposit
    currency        VARCHAR(10) NOT NULL DEFAULT 'ARS'
        CHECK (currency IN ('ARS', 'USD', 'USDT', 'EUR')),
    merchant_raw    TEXT,                            -- Original merchant string from statement
    merchant_clean  VARCHAR(200),                   -- Normalized merchant name
    description     TEXT,                            -- Full description from statement
    category        VARCHAR(50),                    -- Assigned category (may be NULL if pending HITL)
    category_score  DECIMAL(3, 2),                  -- Classifier confidence (0.00–1.00)
    category_source VARCHAR(20) DEFAULT 'auto'      -- 'auto', 'user', 'hitl'
        CHECK (category_source IN ('auto', 'user', 'hitl')),
    is_flagged      BOOLEAN DEFAULT FALSE,          -- Flagged for HITL review
    import_batch_id UUID,                           -- Links to import_batches
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Duplicate detection constraint
    UNIQUE (account_id, date, amount, merchant_raw)
);

CREATE INDEX idx_transactions_date ON transactions(date DESC);
CREATE INDEX idx_transactions_category ON transactions(category) WHERE category IS NOT NULL;
CREATE INDEX idx_transactions_flagged ON transactions(is_flagged) WHERE is_flagged = TRUE;
CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_import ON transactions(import_batch_id);
```

### `import_batches`
```sql
CREATE TABLE import_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    file_name       VARCHAR(255) NOT NULL,
    file_hash       VARCHAR(64) NOT NULL,           -- SHA-256 of imported file
    row_count       INTEGER NOT NULL,
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    parser_used     VARCHAR(50) NOT NULL,            -- 'santander_csv', 'galicia_csv', etc.
    status          VARCHAR(20) DEFAULT 'completed'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);
```

### `assets`
```sql
CREATE TABLE assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    asset_type      VARCHAR(30) NOT NULL
        CHECK (asset_type IN ('cash', 'cedear', 'stock', 'etf', 'crypto', 'bond', 'fci')),
    ticker          VARCHAR(20),                    -- e.g., "AAPL", "QQQ.BA", "USDT"
    quantity        DECIMAL(18, 8) NOT NULL DEFAULT 0,
    avg_cost_usd    DECIMAL(18, 2),                 -- Average cost basis in USD
    last_price_usd  DECIMAL(18, 4),                 -- Last known price in USD
    last_price_at   TIMESTAMPTZ,                    -- When price was last updated
    currency        VARCHAR(10) NOT NULL DEFAULT 'USD',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assets_ticker ON assets(ticker);
CREATE INDEX idx_assets_type ON assets(asset_type);
CREATE INDEX idx_assets_account ON assets(account_id);
```

### `income_sources`
```sql
CREATE TABLE income_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label           VARCHAR(100) NOT NULL,          -- "Salary - Acme Corp", "Freelance - Upwork"
    type            VARCHAR(30) NOT NULL
        CHECK (type IN ('salary', 'freelance', 'investment', 'rental', 'government', 'other')),
    currency        VARCHAR(10) NOT NULL DEFAULT 'ARS',
    monthly_amount  DECIMAL(18, 2),                 -- Expected monthly amount (NULL if variable)
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### `exchange_rates` (cached)
```sql
CREATE TABLE exchange_rates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rate_type       VARCHAR(20) NOT NULL             -- 'official', 'mep', 'ccl', 'blue', 'crypto'
        CHECK (rate_type IN ('official', 'mep', 'ccl', 'blue', 'crypto')),
    base_currency   VARCHAR(10) NOT NULL DEFAULT 'USD',
    quote_currency  VARCHAR(10) NOT NULL DEFAULT 'ARS',
    buy_rate        DECIMAL(12, 4),
    sell_rate       DECIMAL(12, 4),
    mid_rate        DECIMAL(12, 4) NOT NULL,
    source          VARCHAR(50),                    -- 'bcra', 'ambito', 'coingecko'
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_exchange_rates_type ON exchange_rates(rate_type, fetched_at DESC);
```

### `kb_chunks` (RAG knowledge base)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE kb_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content         TEXT NOT NULL,
    embedding       vector(1024),                   -- Qwen3-embedding dimension (multilingual)
    source          VARCHAR(500),                   -- URL, book title, file path
    source_title    VARCHAR(300),                   -- Document title for precise provenance
    source_type     VARCHAR(30)                     -- 'blog', 'book_summary', 'transcript', 'official_doc'
        CHECK (source_type IN ('blog', 'book_summary', 'transcript', 'official_doc', 'user_note')),
    topic_tags      TEXT[],                         -- PostgreSQL array of tags
    argentina_specific BOOLEAN DEFAULT FALSE,
    chunk_index     INTEGER,                        -- Position within source document
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_kb_chunks_embedding ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_kb_chunks_tags ON kb_chunks USING gin(topic_tags);
CREATE INDEX idx_kb_chunks_argentina ON kb_chunks(argentina_specific) WHERE argentina_specific = TRUE;
```

### `kb_entities` (Graph Database Preparation)
```sql
CREATE TABLE kb_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,           -- e.g., 'Concept', 'Regulation', 'Asset'
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, entity_type)
);

CREATE INDEX idx_kb_entities_name ON kb_entities(name);
CREATE INDEX idx_kb_entities_type ON kb_entities(entity_type);
```

### `kb_relations` (Graph Database Preparation)
```sql
CREATE TABLE kb_relations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    head_entity_id  UUID NOT NULL REFERENCES kb_entities(id) ON DELETE CASCADE,
    tail_entity_id  UUID NOT NULL REFERENCES kb_entities(id) ON DELETE CASCADE,
    relation_type   VARCHAR(100) NOT NULL,          -- e.g., 'REGULATES', 'PART_OF', 'DEPENDS_ON'
    chunk_id        UUID REFERENCES kb_chunks(id) ON DELETE SET NULL,  -- Knowledge provenance
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(head_entity_id, tail_entity_id, relation_type)
);

CREATE INDEX idx_kb_relations_head ON kb_relations(head_entity_id);
CREATE INDEX idx_kb_relations_tail ON kb_relations(tail_entity_id);
```

---

## Curated Semantic Views

These views abstract complex financial logic for the Text-to-SQL generator.

### `v_net_worth`
```sql
CREATE OR REPLACE VIEW v_net_worth AS
WITH latest_rates AS (
    SELECT DISTINCT ON (rate_type)
        rate_type, mid_rate, fetched_at
    FROM exchange_rates
    WHERE quote_currency = 'ARS'
    ORDER BY rate_type, fetched_at DESC
),
cash_by_currency AS (
    SELECT
        currency,
        SUM(amount) as total
    FROM transactions
    GROUP BY currency
),
asset_values AS (
    SELECT
        SUM(quantity * COALESCE(last_price_usd, avg_cost_usd, 0)) as total_assets_usd
    FROM assets
)
SELECT
    COALESCE((SELECT total FROM cash_by_currency WHERE currency = 'ARS'), 0) as total_ars,
    COALESCE((SELECT total FROM cash_by_currency WHERE currency = 'USD'), 0) as total_usd,
    COALESCE((SELECT total_assets_usd FROM asset_values), 0) as total_assets_usd,
    COALESCE((SELECT total FROM cash_by_currency WHERE currency = 'ARS'), 0) /
        NULLIF((SELECT mid_rate FROM latest_rates WHERE rate_type = 'mep'), 0) +
        COALESCE((SELECT total FROM cash_by_currency WHERE currency = 'USD'), 0) +
        COALESCE((SELECT total_assets_usd FROM asset_values), 0) as total_usd_equivalent,
    (SELECT fetched_at FROM latest_rates WHERE rate_type = 'mep') as rate_timestamp;
```

### `v_monthly_burn`
```sql
CREATE OR REPLACE VIEW v_monthly_burn AS
SELECT
    DATE_TRUNC('month', date) as month,
    category,
    currency,
    COUNT(*) as tx_count,
    SUM(ABS(amount)) as total_spend,
    AVG(ABS(amount)) as avg_transaction
FROM transactions
WHERE amount < 0
    AND date >= CURRENT_DATE - INTERVAL '3 months'
GROUP BY DATE_TRUNC('month', date), category, currency
ORDER BY month DESC, total_spend DESC;
```

### `v_cedear_exposure`
```sql
CREATE OR REPLACE VIEW v_cedear_exposure AS
SELECT
    a.ticker,
    a.quantity,
    a.avg_cost_usd,
    a.last_price_usd,
    a.quantity * a.last_price_usd as current_value_usd,
    (a.last_price_usd - a.avg_cost_usd) / NULLIF(a.avg_cost_usd, 0) * 100 as pnl_pct,
    a.last_price_at
FROM assets a
WHERE a.asset_type = 'cedear';
```

### `v_income_summary`
```sql
CREATE OR REPLACE VIEW v_income_summary AS
SELECT
    is2.label,
    is2.type,
    is2.currency,
    is2.monthly_amount as expected_monthly,
    COALESCE(actual.actual_monthly, 0) as actual_monthly_avg
FROM income_sources is2
LEFT JOIN LATERAL (
    SELECT AVG(amount) as actual_monthly
    FROM transactions t
    WHERE t.amount > 0
        AND t.category = 'Income'
        AND t.date >= CURRENT_DATE - INTERVAL '3 months'
) actual ON TRUE
WHERE is2.is_active = TRUE;
```

### `v_category_spend`
```sql
CREATE OR REPLACE VIEW v_category_spend AS
SELECT
    category,
    currency,
    DATE_TRUNC('month', date) as month,
    COUNT(*) as transaction_count,
    SUM(ABS(amount)) as total_amount,
    AVG(ABS(amount)) as avg_amount,
    MIN(ABS(amount)) as min_amount,
    MAX(ABS(amount)) as max_amount
FROM transactions
WHERE amount < 0
    AND category IS NOT NULL
GROUP BY category, currency, DATE_TRUNC('month', date)
ORDER BY month DESC, total_amount DESC;
```

---

## Synthetic Data Generator

A Python script using **Faker** and **NumPy** will be provided at `data/synthetic/generate.py`. It will:

1. Create 3–5 sample accounts (checking ARS, savings USD, crypto wallet, brokerage)
2. Generate 6 months of realistic transactions (~200–400 per month)
3. Seed exchange rates with historical-like MEP/official spreads
4. Create sample assets (CEDEARs, ETFs, USDT holdings)
5. Insert income sources
6. Output: SQL INSERT statements or direct DB seeding via `psycopg`

---

## Docker Compose

```yaml
version: "3.9"
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: aegis_finance
      POSTGRES_USER: aegis
      POSTGRES_PASSWORD: ${AEGIS_DB_PASSWORD:-aegis_dev}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql:/docker-entrypoint-initdb.d  # Auto-runs DDL on first init

volumes:
  pgdata:
```
