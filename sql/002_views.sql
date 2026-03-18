-- =============================================================================
-- Aegis Finance — Curated Semantic Views
-- File: sql/002_views.sql
-- Description: Abstraction views for Text-to-SQL and dashboard queries.
-- =============================================================================

-- ── v_net_worth ─────────────────────────────────────────────────────────────

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

-- ── v_monthly_burn ──────────────────────────────────────────────────────────

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

-- ── v_cedear_exposure ───────────────────────────────────────────────────────

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

-- ── v_income_summary ────────────────────────────────────────────────────────

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

-- ── v_category_spend ────────────────────────────────────────────────────────

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
