# Aegis Finance — Architecture Specification
**Version:** 0.3 | **Status:** Draft | **Scope:** MVP (Milestones 1–3)

---

## 1. Revised Split-Brain Model

The original PRD described a Local SLM + Cloud LLM split. With Qwen 3.5 running locally on an NVIDIA GPU via llama.cpp, the architecture consolidates: the local layer is now capable enough to handle SQL generation, PII scrubbing, and RAG synthesis without a cloud dependency for those tasks. The cloud LLM role is narrowed to high-complexity market reasoning only. Qwen 3.5 was chosen for its strong multilingual (Spanish/English) performance.

```
┌─────────────────────────────────────────────────────────┐
│                    USER (Gradio UI)                     │
└───────────────────────────┬─────────────────────────────┘
                            │ natural language query
                            ▼
┌─────────────────────────────────────────────────────────┐
│              LANGGRAPH ORCHESTRATOR                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │  Router  │→ │ SQL Flow │  │ RAG Flow │  │Privacy │ │
│  │  Node    │  │          │  │          │  │  Node  │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
└──────────────────────┬──────────────────────────────────┘
           ┌───────────┴────────────┐
           ▼                        ▼
┌─────────────────────┐  ┌─────────────────────────────┐
│    LOCAL LAYER      │  │       CLOUD LAYER            │
│                     │  │  (Anonymized inputs only)    │
│  Qwen 3.5           │  │                              │
│  (llama.cpp, GPU)   │  │  Cloud LLM (provider-agnostic)│
│                     │  │  → Market synthesis          │
│  PostgreSQL         │  │  → Complex multi-step        │
│  pgvector           │  │    financial planning        │
└─────────────────────┘  └─────────────────────────────┘
```

**Cloud LLM provider rationale:**  
For a privacy-first product targeting a "Sovereign Investor" persona, routing data through a cloud provider is a trust and marketing problem regardless of technical safeguards. The cloud provider is now **configurable**: OpenAI, Anthropic, or Google Gemini. A local fallback (Qwen 3.5) is available when no cloud API key is configured.

---

## 2. LangGraph Flow: Node-by-Node Specification

### 2.1 Router Node

**Role:** Classifies the incoming query and dispatches to the correct subgraph.

**Input:** `{ query: str, conversation_history: list }`

**Logic (runs on Qwen 3.5 locally):**

```
Query type detection → one of:
  - PERSONAL_FINANCIAL   → SQL Flow + optional RAG
  - MARKET_KNOWLEDGE     → RAG Flow (local KB first, market API if stale)
  - HYBRID               → SQL Flow → Privacy Node → Cloud LLM
  - GENERAL_FINANCE      → Local RAG only (no SQL, no cloud)
```

**Output:** `{ route: str, query_type: str, requires_cloud: bool }`

**Design note:** The router decision is made locally. This is the first firewall — the cloud LLM is never invoked unless `requires_cloud = True` AND the Privacy Node has already sanitized the payload.

---

### 2.2 Text-to-SQL Flow

This is the hardest engineering problem in the system. Small models generating SQL against financial schemas fail in predictable ways: hallucinated column names, incorrect aggregations on multi-currency data, invalid joins across `assets` and `transactions`.

#### Generation Step

**Prompt construction:**
```
System: You are a SQL generator. Output ONLY valid PostgreSQL SQL.
        You may ONLY query these views: {injected_view_definitions}
        Do NOT reference base tables directly.
        Do NOT use INSERT, UPDATE, DELETE, DROP.

User: {natural_language_query}
```

Injecting only relevant view definitions (not the full schema) is critical — it bounds the model's output space and reduces hallucination rate. Use semantic similarity against view descriptions to select which views to inject (pgvector lookup).

#### Validation Loop

```
┌────────────────────────────────────────┐
│          SQL VALIDATION LOOP           │
│                                        │
│  1. SYNTAX CHECK                       │
│     psycopg2 parse (no execution)      │
│     → Fail: return error to model      │
│                                        │
│  2. SCHEMA CHECK                       │
│     Verify all referenced names exist  │
│     in the allowed views whitelist     │
│     → Fail: return specific error      │
│                                        │
│  3. DRY RUN                            │
│     Execute with EXPLAIN (no rows)     │
│     → Fail: return planner error       │
│                                        │
│  4. SANITY CHECK                       │
│     Row count > 0?                     │
│     All currency columns consistent?  │
│     → Warn if ARS/USD mixed without   │
│       explicit conversion              │
│                                        │
│  Max retries: 3                        │
│  On 3rd failure: surface to user with │
│  "I couldn't generate a reliable      │
│   query for this — try rephrasing"    │
└────────────────────────────────────────┘
```

**Error feedback format (passed back to model on retry):**
```python
{
  "previous_sql": "...",
  "error_type": "SCHEMA_VIOLATION",
  "error_detail": "Column 'balance' does not exist in v_net_worth. Available: total_ars, total_usd, total_usd_equivalent",
  "attempt": 2
}
```

**Argentine-specific SQL consideration:**  
The `transactions` table must include a `currency` column (`ARS | USD | USDT`). All aggregation views must expose both raw and USD-equivalent values. The validation layer should warn (not fail) when a query aggregates across currencies without a conversion node.

#### Curated Views (DDL summary — full DDL in separate file)

| View | Purpose | Sensitive? |
|------|---------|------------|
| `v_net_worth` | Total assets by currency and type | Yes — masked before cloud |
| `v_monthly_burn` | Avg spend by category, last 3 months | Yes |
| `v_cedear_exposure` | CEDEAR positions, ticker, quantity, USD value | Yes |
| `v_income_summary` | Salary + freelance income streams | Yes |
| `v_category_spend` | Spending by merchant category (anonymized labels) | Partial |

---

### 2.3 Privacy Middleware Node

This node sits between any local result and the Cloud LLM. It is never bypassed.

**Contract:**

```python
Input:  PrivacyInput(
    query: str,               # original user query
    sql_result: dict | None,  # query result if SQL flow ran
    context_chunks: list[str] # RAG chunks if retrieval ran
)

Output: PrivacyOutput(
    sanitized_query: str,
    sanitized_context: str,
    redaction_map: dict,      # stored locally, never sent upstream
    risk_score: float         # 0.0–1.0, logged for Leakage Ratio KPI
)
```

**Two-pass scrubbing:**

**Pass 1 — Regex (deterministic, fast):**
```python
PATTERNS = {
    "CUIT":        r"\b\d{2}-\d{8}-\d{1}\b",
    "CBU":         r"\b\d{22}\b",
    "EXACT_ARS":   r"\$\s?[\d\.,]+\s?(ARS|pesos)?",
    "EXACT_USD":   r"(USD|u\$s|US\$)\s?[\d\.,]+",
    "FULL_NAME":   r"\b[A-Z][a-z]+ [A-Z][a-z]+\b",  # heuristic
    "EMAIL":       r"[\w\.-]+@[\w\.-]+\.\w+",
}
```

Exact monetary values are replaced with **range buckets**, not `[REDACTED]`. This preserves reasoning utility:

```
$2,450,000 ARS  →  [MED_ARS_VALUE]     # 500k–5M ARS
$45,000 USD     →  [HIGH_USD_VALUE]    # >$20k USD
```

Range thresholds are defined in `config.yaml` and can be tuned.

**Pass 2 — Qwen 3.5 semantic scrub:**
```
System: You are a PII auditor. Review the following text and identify
        any remaining personally identifiable or financially sensitive
        information that was not already masked with [...] tokens.
        Replace any found with appropriate [CATEGORY] tokens.
        Output ONLY the cleaned text, no explanation.

User: {pass_1_output}
```

**Pass 2 catches:** indirect identifiers ("my daughter's school fees," "the property in Palermo"), relative amounts that could de-anonymize ("I spent double what I earn"), and named entities that regex missed.

**Redaction map** (stored in local SQLite, session-scoped):
```json
{
  "HIGH_USD_VALUE_1": 45000,
  "MED_ARS_VALUE_1": 2450000,
  "PERSON_1": "María González"
}
```

This map is used to reconstruct concrete values in the final response shown to the user, after the cloud response is received.

**Risk score calculation:**  
After Pass 2, run the output through a lightweight PII scanner (e.g., `presidio-analyzer` locally). Count residual hits / total tokens = `risk_score`. If `risk_score > 0.05`, block the cloud call and surface a warning.

---

### 2.4 RAG Retrieval Flow

Two retrieval paths with explicit routing logic.

```
┌─────────────────────────────────────────────┐
│              RAG ROUTER                     │
│                                             │
│  "What is a CEDEAR?"                        │
│    → LOCAL KB ONLY                          │
│                                             │
│  "What's the MEP dollar today?"             │
│    → MARKET API ONLY OR SEARCH              │
│                                             │
│  "Should I rebalance given ARS inflation?"  │
│    → LOCAL KB + MARKET API + CLOUD LLM      │
└──────────────┬───────────────┬──────────────┘
               ▼               ▼
   ┌───────────────────┐  ┌───────────────────┐
   │   LOCAL KB        │  │   MARKET DATA     │
   │   (pgvector)      │  │   ADAPTERS        │
   │                   │  │                   │
   │ - Argentine tax   │  │ - BCRA (official) │
   │   law summaries   │  │ - MEP/CCL rates   │
   │ - CEDEAR mechanics│  │ - BCBA/BYMA data  │
   │ - Financial       │  │ - Yahoo Finance   │
   │   planning docs   │  │   (USD assets)    │
   │ - User's own      │  │                   │
   │   annotations     │  │ Staleness TTL:    │
   │                   │  │ prices = 15 min   │
   └───────────────────┘  │ rates  = 1 hr     │
                          └───────────────────┘
```

**Local KB ingestion pipeline (offline, not part of query flow):**
```
Source docs (PDF/HTML/MP3) 
  → Chunking (512 tokens, 64 overlap) 
  → Qwen3-embedding (via llama.cpp embed endpoint) 
  → pgvector storage with metadata: {source, date, topic_tags, argentina_specific: bool}
```

**Retrieval at query time:**
```python
# 1. Embed the query locally
query_embedding = llama_cpp.embed(model="qwen3-embedding", prompt=query)

# 2. Retrieve top-k chunks
chunks = pgvector.similarity_search(query_embedding, k=5, 
                                     filter={"argentina_specific": True} if applicable)

# 3. Staleness check on market data
if market_data_age > TTL:
    fetch_fresh_market_data()  # API call, no PII involved

# 4. Merge and rank
context = rerank(chunks + market_snippets)  # cross-encoder rerank via local model
```

**Staleness Guardrail (from PRD):**  
Implemented as a LangGraph node that checks `last_transaction_import` timestamp. If `> 30 days`, the graph injects a warning banner into the Gradio UI and appends a disclaimer to every SQL-based answer. It does NOT block the query — blocking would hurt UX for users who use the knowledge-only features.

---

## 3. Component Summary

| Component | Technology | Runs Where |
|-----------|-----------|------------|
| Orchestrator | LangGraph | Local |
| Local LLM | Qwen 3.5 via llama.cpp | Local GPU |
| Cloud LLM | Provider-agnostic (OpenAI / Anthropic / Gemini / local fallback) | Cloud (anonymized) |
| Database | PostgreSQL + pgvector | Local Docker |
| UI | Gradio | Local (localhost) |
| PII Scanner | Microsoft Presidio | Local |
| Market APIs | BCRA, BYMA, Yahoo Finance | External (no PII) |
| Embeddings | Qwen3-embedding / Qwen3-VL-Embedding (OCR fallback) via llama.cpp | Local GPU |

---

## 4. Open Questions (to resolve before Milestone 2)

1. **Embedding model:** Qwen3-embedding is the primary embedding model. Qwen3-VL-Embedding serves as OCR fallback when text extraction from PDFs/images fails. Verify both run via llama.cpp embed endpoint with correct dimensions (1024).

2. **Redaction map persistence:** Session-scoped SQLite is simple but means the user loses response reconstruction if they close the app. Should it persist across sessions (encrypted at rest)?

3. **Cloud LLM fallback:** If the user has no API key configured, does the system degrade gracefully to local-only mode? This matters for the OSS contributor persona who won't have a paid key.

4. **MEP/CCL data source:** BYMA has no free public API. Options: scrape `ambito.com`, use `pycoingecko` for USDT as a CCL proxy, or require manual entry. This needs a decision before Milestone 1 DDL is finalized.
