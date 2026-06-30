# yfinance Reference — NSE Equities

Investigation date: 2026-06-30  
yfinance version: **1.5.1**  
Sample tickers: **RELIANCE.NS** (Energy), **TCS.NS** (IT), **INFY.NS** (IT, ADR-style reporting)

This document records actual return shapes from yfinance for Indian NSE tickers and maps them to our DuckDB schema (`src/database/schema.sql`). Use this instead of re-discovering field availability during ingestion work.

---

## Step 1 — yfinance Return Shapes

### General conventions

| Aspect | Actual behavior |
|--------|-----------------|
| Ticker input | Use Yahoo suffix: `RELIANCE.NS`, `TCS.NS`, etc. |
| `Ticker.info` | `dict[str, Any]` — ~172 keys for all three sample tickers; types are mostly `str`, `int`, `float`, `bool`; some `None` |
| Financial statements | `pd.DataFrame` — **rows = line items** (index), **columns = period-end dates** (`datetime64[s]`). Must be transposed to produce one row per period for our schema. |
| Annual depth | 5 fiscal periods returned (latest often partially null — incomplete current FY) |
| Quarterly depth | 3–6 periods depending on ticker/statement; highly variable |
| Nulls | Missing line items → row absent from index; present-but-unknown → `NaN` in cells. Latest column frequently all-`NaN` for many rows. |
| Newer camelCase APIs | `get_income_stmt()`, `get_balance_sheet()`, `get_cashflow()` exist but use different row labels (e.g. `TaxEffectOfUnusualItems`). **Use legacy properties** (`.financials`, etc.) for consistent Title Case labels — matches community docs and our mapping below. |

---

### `Ticker.info` — company profile / master data

**Return type:** `dict` (can be empty `{}` on network failure; normally 172 keys for NSE large-caps)

**Relevant fields observed (all three tickers unless noted):**

| Field | Type | Sample (RELIANCE.NS) | Notes |
|-------|------|----------------------|-------|
| `symbol` | `str` | `"RELIANCE.NS"` | Includes `.NS` suffix |
| `shortName` | `str` | `"RELIANCE INDUSTRIES LTD"` | |
| `longName` | `str` | `"Reliance Industries Limited"` | Preferred for `company_name` |
| `exchange` | `str` | `"NSI"` | Yahoo internal code, **not** `"NSE"` |
| `fullExchangeName` | `str` | `"NSE"` | Use to derive `exchange = 'NSE'` |
| `market` | `str` | `"in_market"` | |
| `country` | `str` | `"India"` | |
| `currency` | `str` | `"INR"` | Quote / price currency |
| `financialCurrency` | `str` | `"INR"` (RELIANCE, TCS); **`"USD"` (INFY)** | Statement reporting currency — **critical** |
| `sector` | `str` | `"Energy"` | |
| `industry` | `str` | `"Oil & Gas Refining & Marketing"` | |
| `quoteType` | `str` | `"EQUITY"` | |
| `sharesOutstanding` | `int` | `13532472634` | Present for all 3 |
| `impliedSharesOutstanding` | `int` | `13532472635` | Present for all 3 |
| `firstTradeDateEpochUtc` | `None` | `None` | **Always null** in sample |
| `firstTradeDateMilliseconds` | `int` | `820467900000` | Use for `listing_date` (epoch ms → date) |
| `isin` | — | **Key absent entirely** | Not in `info` for any sample ticker |
| `corporateActions` | `list` | `[]` | Empty list in `info`; real data is in `.actions` |

**Not useful for our schema but present:** `marketCap`, `totalRevenue`, `ebitda`, `trailingEps`, etc. — these are TTM/spot snapshots, not historical statement rows. Do not mix with `financials` table.

---

### `Ticker.financials` / `Ticker.quarterly_financials` — income statement

**Return type:** `pd.DataFrame` (rows = line items, columns = period-end `Timestamp`)

**Shapes observed:**

| Ticker | Annual | Quarterly |
|--------|--------|-----------|
| RELIANCE.NS | 50 × 5 | 37 × 5 |
| TCS.NS | 48 × 5 | 48 × 5 |
| INFY.NS | 53 × 5 | 51 × 6 |

**Column dtype:** `datetime64[s]` (period end dates, e.g. `2025-03-31` for Indian FY end)

**Cell dtype:** `float64` (line item amounts and per-share figures)

**Row labels (line items) — union across 3 tickers, 60 unique annual / 56 quarterly:**

Key rows that map to our schema (Title Case, consistent across all 3 for annual):

| Row label | Present |
|-----------|---------|
| `Total Revenue` | All 3 (annual + quarterly) |
| `Cost Of Revenue` | All 3 |
| `Gross Profit` | All 3 |
| `Operating Expense` | All 3 — singular, not "Operating Expenses" |
| `Operating Income` | All 3 |
| `EBITDA` | All 3 |
| `EBIT` | All 3 |
| `Interest Expense` | All 3 |
| `Pretax Income` | All 3 |
| `Tax Provision` | All 3 |
| `Net Income` | All 3 |
| `Basic EPS` | All 3 |
| `Diluted EPS` | All 3 |
| `Basic Average Shares` | All 3 (often `NaN` on latest period) |
| `Diluted Average Shares` | All 3 (often `NaN` on latest period) |

**Additional rows returned** (not mapped to our schema): `Operating Revenue`, `Total Expenses`, `Normalized Income`, `Net Interest Income`, `Interest Income`, depreciation/reconciliation items, etc. — 40+ extra rows per ticker.

**Null pattern:** Latest annual column (e.g. `2026-03-31`) is frequently all-`NaN` for key rows — incomplete current fiscal year.

---

### `Ticker.balance_sheet` / `Ticker.quarterly_balance_sheet`

**Return type:** same orientation as financials

**Shapes observed:**

| Ticker | Annual | Quarterly |
|--------|--------|-----------|
| RELIANCE.NS | 77 × 5 | 77 × 3 |
| TCS.NS | 81 × 5 | 80 × 3 |
| INFY.NS | 92 × 5 | 91 × 6 |

**Key row labels:**

| Row label | RELIANCE | TCS | INFY |
|-----------|----------|-----|------|
| `Total Assets` | ✓ | ✓ | ✓ |
| `Current Assets` | ✓ | ✓ | ✓ |
| `Total Non Current Assets` | ✓ | ✓ | ✓ |
| `Cash And Cash Equivalents` | ✓ | ✓ | ✓ |
| `Inventory` | ✓ | ✓ | **row absent** |
| `Accounts Receivable` | ✓ | ✓ | ✓ |
| `Total Liabilities Net Minority Interest` | ✓ | ✓ | ✓ |
| `Current Liabilities` | ✓ | ✓ | ✓ |
| `Total Non Current Liabilities Net Minority Interest` | ✓ | ✓ | ✓ |
| `Total Debt` | ✓ | ✓ | ✓ |
| `Current Debt` | ✓ | **row absent** | **row absent** |
| `Long Term Debt` | ✓ | **row absent** | **row absent** |
| `Stockholders Equity` | ✓ | ✓ | ✓ |
| `Retained Earnings` | ✓ | ✓ | ✓ |

**Quarterly sparsity:** RELIANCE quarterly balance sheet — only 2/3 periods non-null for key rows. TCS and INFY are better but still have null latest periods.

---

### `Ticker.cashflow` / `Ticker.quarterly_cashflow`

**Return type:** same orientation as financials

**Shapes observed:**

| Ticker | Annual | Quarterly |
|--------|--------|-----------|
| RELIANCE.NS | 47 × 5 | **empty (0 × 0)** |
| TCS.NS | 50 × 5 | 39 × **1** |
| INFY.NS | 51 × 5 | 51 × 5 |

**Key row labels (annual — all 3 tickers):**

| Row label | Notes |
|-----------|-------|
| `Operating Cash Flow` | Direct map |
| `Investing Cash Flow` | Direct map |
| `Financing Cash Flow` | Direct map |
| `Changes In Cash` | Map to `net_cash_flow` |
| `Free Cash Flow` | Direct map |
| `Capital Expenditure` | Direct map (typically negative = outflow) |
| `End Cash Position` | Not in our schema |

**Quarterly cash flow is the weakest dataset** — completely missing for RELIANCE, single period for TCS, partial nulls for INFY.

---

### `Ticker.history` — price data

**Return type:** `pd.DataFrame` indexed by `DatetimeIndex` (timezone-aware: `Asia/Kolkata`, `+05:30`)

**Default call:** `ticker.history(start=..., end=...)` uses `auto_adjust=True` (yfinance default since recent versions).

| `auto_adjust` | Columns returned | dtypes |
|---------------|------------------|--------|
| `True` (default) | `Open`, `High`, `Low`, `Close`, `Volume`, `Dividends`, `Stock Splits` | OHLC `float64`, `Volume` `int64`, `Dividends`/`Stock Splits` `float64` |
| `False` | Above + **`Adj Close`** | `Adj Close` `float64` |

**No `Adj Close` when `auto_adjust=True`** — Close is already adjusted; Open/High/Low may still be unadjusted depending on version. For our schema (`adj_close` column), **call with `auto_adjust=False`** and map `Adj Close` → `adj_close`, `Close` → `close`.

**Units:** INR per share (confirmed via `info.currency = "INR"`). Volume is share count.

**Sample row (RELIANCE.NS, 2026-06-30):** Open=1306.90, Close=1293.90, Volume=int, Dividends=0.0, Stock Splits=0.0

---

### Corporate actions (related, not in Step 3 wrapper scope)

Available via `Ticker.actions` (`DataFrame`), `Ticker.dividends` (`Series`), `Ticker.splits` (`Series`):

```
actions columns: Dividends (float64), Stock Splits (float64)
index: timezone-aware DatetimeIndex
```

- **Dividends:** per-share amount in INR (e.g. TCS: 57.0, 31.0)
- **Stock Splits:** ratio as float (e.g. `2.0` = 2-for-1). No `record_date`, `payment_date`, or `ex_date` as separate fields — only the action `Date` index.
- **Bonus issues:** not distinguished from splits; no `buyback` data observed.
- `info.corporateActions` is always `[]` — do not use.

---

## Step 2 — Schema Mapping & Gap Analysis

### Derived fields (not from yfinance directly)

These schema columns must be computed in the wrapper or ingestion layer:

| Schema column | Derivation |
|---------------|------------|
| `company_id` | DB-assigned; not from yfinance |
| `symbol` | Strip `.NS` from ticker → `RELIANCE` |
| `exchange` | Map `fullExchangeName` (`"NSE"`) or hardcode `"NSE"` for `.NS` tickers |
| `fiscal_year` | From `period_end_date` (India: FY ending Mar → FY = year of Mar date) |
| `fiscal_quarter` | From `period_end_date` month: Q1=Jun, Q2=Sep, Q3=Dec, Q4=Mar (null for annual) |
| `period_type` | `'annual'` or `'quarterly'` based on which property was fetched |
| `source` | `'yfinance'` |
| `created_at` / `updated_at` / `ingested_at` | Set at ingestion time |

---

### Table: `companies`

| Schema column | yfinance source | Status |
|---------------|-----------------|--------|
| `company_id` | — | DB-generated |
| `symbol` | `info["symbol"]` → strip `.NS` | ✓ |
| `exchange` | `info["fullExchangeName"]` → `"NSE"` | ✓ (normalize from `"NSI"`) |
| `country` | `info["country"]` | ✓ |
| `isin` | — | **GAP: key absent from `info` for all 3 tickers** |
| `company_name` | `info["longName"]` (fallback `shortName`) | ✓ |
| `sector` | `info["sector"]` | ✓ |
| `industry` | `info["industry"]` | ✓ |
| `shares_outstanding` | `info["sharesOutstanding"]` | ✓ (int, all 3 present) |
| `shares_diluted` | `info["impliedSharesOutstanding"]` | ✓ (best available; not from statements) |
| `listing_date` | `info["firstTradeDateMilliseconds"]` / 1000 → date | ✓ (`firstTradeDateEpochUtc` is null) |
| `is_active` | — | Default `True`; yfinance has no delisting flag |
| `source` | hardcode `'yfinance'` | ✓ |

---

### Table: `prices`

| Schema column | yfinance source | Status |
|---------------|-----------------|--------|
| `company_id` | — | DB join |
| `trade_date` | `history` index → date (strip tz) | ✓ |
| `open` | `history["Open"]` | ✓ float64 |
| `high` | `history["High"]` | ✓ |
| `low` | `history["Low"]` | ✓ |
| `close` | `history["Close"]` | ✓ — use `auto_adjust=False` for unadjusted close |
| `volume` | `history["Volume"]` | ✓ int64 |
| `adj_close` | `history["Adj Close"]` | ✓ only when `auto_adjust=False`; **null if default call** |
| `source` | hardcode `'yfinance'` | ✓ |

---

### Table: `financials`

| Schema column | yfinance row label | Status |
|---------------|-------------------|--------|
| `company_id` | — | DB join |
| `period_end_date` | statement column `Timestamp` → date | ✓ |
| `period_type` | `'annual'` / `'quarterly'` | derived |
| `fiscal_year` | derived from period_end_date | derived |
| `fiscal_quarter` | derived (null for annual) | derived |
| `currency` | `info["financialCurrency"]` | ✓ — **see currency warning below** |
| `revenue` | `Total Revenue` | ✓ |
| `cost_of_revenue` | `Cost Of Revenue` | ✓ |
| `gross_profit` | `Gross Profit` | ✓ |
| `operating_expenses` | `Operating Expense` | ✓ (singular label) |
| `operating_profit` | `Operating Income` | ✓ |
| `ebitda` | `EBITDA` | ✓ |
| `ebit` | `EBIT` | ✓ |
| `interest_expense` | `Interest Expense` | ✓ |
| `profit_before_tax` | `Pretax Income` | ✓ |
| `tax_expense` | `Tax Provision` | ✓ |
| `net_profit` | `Net Income` | ✓ |
| `eps_basic` | `Basic EPS` | ✓ (per-share, not currency-scaled) |
| `eps_diluted` | `Diluted EPS` | ✓ |
| `source` | hardcode `'yfinance'` | ✓ |

**Gaps / quality notes:**
- Latest annual period often all-`NaN` (incomplete FY) — expect ~4 usable annual rows, not 5.
- `Basic Average Shares` / `Diluted Average Shares` rows exist but are frequently `NaN` on the latest period; not mapped to schema (we use `info` for share counts on `companies` instead).
- No separate `operating_revenue` column in schema; `Operating Revenue` row exists in yfinance but is redundant with `Total Revenue` for these tickers.

---

### Table: `balance_sheets`

| Schema column | yfinance row label | Status |
|---------------|-------------------|--------|
| `company_id` | — | DB join |
| `period_end_date` | column `Timestamp` → date | ✓ |
| `period_type` | derived | derived |
| `fiscal_year` / `fiscal_quarter` | derived | derived |
| `currency` | `info["financialCurrency"]` | ✓ |
| `total_assets` | `Total Assets` | ✓ |
| `current_assets` | `Current Assets` | ✓ |
| `non_current_assets` | `Total Non Current Assets` | ✓ |
| `cash_and_equivalents` | `Cash And Cash Equivalents` | ✓ |
| `inventory` | `Inventory` | **Sparse: row absent for INFY** (expected for IT) |
| `receivables` | `Accounts Receivable` | ✓ |
| `total_liabilities` | `Total Liabilities Net Minority Interest` | ✓ |
| `current_liabilities` | `Current Liabilities` | ✓ |
| `non_current_liabilities` | `Total Non Current Liabilities Net Minority Interest` | ✓ |
| `total_debt` | `Total Debt` | ✓ |
| `short_term_debt` | `Current Debt` | **GAP for TCS, INFY** — row absent; leave null |
| `long_term_debt` | `Long Term Debt` | **GAP for TCS, INFY** — row absent; leave null |
| `total_equity` | `Stockholders Equity` | ✓ |
| `retained_earnings` | `Retained Earnings` | ✓ |
| `source` | hardcode `'yfinance'` | ✓ |

**Gaps / quality notes:**
- RELIANCE quarterly: only 2/3 periods have non-null values for key balance sheet rows.
- Debt breakdown (`Current Debt`, `Long Term Debt`) less available than `Total Debt` — do not derive short/long from total; leave null.

---

### Table: `cash_flows`

| Schema column | yfinance row label | Status |
|---------------|-------------------|--------|
| `company_id` | — | DB join |
| `period_end_date` | column `Timestamp` → date | ✓ |
| `period_type` | derived | derived |
| `fiscal_year` / `fiscal_quarter` | derived | derived |
| `currency` | `info["financialCurrency"]` | ✓ |
| `operating_cash_flow` | `Operating Cash Flow` | ✓ annual; quarterly sparse |
| `investing_cash_flow` | `Investing Cash Flow` | ✓ annual; quarterly sparse |
| `financing_cash_flow` | `Financing Cash Flow` | ✓ annual; quarterly sparse |
| `net_cash_flow` | `Changes In Cash` | ✓ (not `End Cash Position`) |
| `capex` | `Capital Expenditure` | ✓ (typically negative) |
| `free_cash_flow` | `Free Cash Flow` | ✓ annual; quarterly sparse |
| `source` | hardcode `'yfinance'` | ✓ |

**Gaps / quality notes — most severe schema gaps:**
- **RELIANCE `quarterly_cashflow`:** completely empty DataFrame.
- **TCS `quarterly_cashflow`:** only **1 period** returned.
- **INFY `quarterly_cashflow`:** 5 periods but 4/5 non-null for key rows.
- Annual cash flow is reliable for all 3 tickers (5 columns, 4 usable after dropping incomplete latest).

---

### Table: `corporate_actions` (future ingestion — not in wrapper scope)

| Schema column | yfinance source | Status |
|---------------|-----------------|--------|
| `action_date` | `actions` index → date | ✓ |
| `action_type` | infer from `Dividends > 0` → `'dividend'`; `Stock Splits > 0` → `'split'` | partial |
| `ex_date` | — | **GAP: not provided** (only one date in index) |
| `record_date` | — | **GAP** |
| `payment_date` | — | **GAP** |
| `currency` | `info["currency"]` | ✓ INR |
| `amount` | `actions["Dividends"]` | ✓ per-share INR |
| `ratio_from` / `ratio_to` | `actions["Stock Splits"]` | **Partial:** yfinance gives denominator-style ratio (2.0 = 2:1); must map to `ratio_from=1, ratio_to=2` |
| `description` | — | **GAP** |
| `bonus` / `buyback` | — | **GAP: not available** |

---

## Units & Currency

| Data | Unit / currency | Notes |
|------|-----------------|-------|
| Price OHLCV | **INR per share** | `info.currency = "INR"` for all 3 |
| Volume | Shares | `int64` |
| Statement amounts | **`info.financialCurrency`** | Absolute values in **raw units** (not crores/lakhs). E.g. RELIANCE FY revenue ≈ 10.57 trillion INR (`10,572,190,000,000`) |
| EPS | Per-share | Not scaled by currency unit |
| INFY statements | **USD** | `financialCurrency = "USD"` while `currency = "INR"` for quotes. Revenue ~$20.2B USD vs TCS ~₹2.67T INR. **Must store `currency` column correctly; do not assume INR for all NSE tickers.** |
| Market cap (info) | INR | `marketCap` in INR despite INFY USD statements |

**Scale:** Values are full rupee/dollar amounts (not in crores). Consistent with `info.totalRevenue` matching statement `Total Revenue` magnitude.

---

## Known NSE / yfinance Weak Spots (summary)

Priority issues to handle in wrapper (null-preserving) and flag in ingestion:

1. **ISIN** — not available in `info` for any sample ticker.
2. **INFY (and potentially other dual-listed ADRs) report financials in USD**, not INR.
3. **Quarterly cash flow** — unreliable or missing (RELIANCE empty, TCS 1 quarter).
4. **Debt breakdown** — `Current Debt` / `Long Term Debt` absent for asset-light IT names; only `Total Debt` available.
5. **Latest period nulls** — most recent annual column is often incomplete across all statement types.
6. **Quarterly balance sheet depth** — RELIANCE returns only 3 quarterly columns with sparse data.
7. **`adj_close`** — requires `auto_adjust=False` on `history()`; default omits the column.
8. **`exchange` code** — `info.exchange` is `"NSI"`, not `"NSE"`; use `fullExchangeName`.
9. **Corporate actions** — dividends/splits only; no bonus/buyback, no ex/record/payment dates.
10. **Statement history depth** — only ~4–5 annual periods; not suitable for long backtests without another source.

---

## Wrapper Design Notes (for Step 3)

When `src/api/yfinance_client.py` is built:

1. Use `yf.Ticker("{symbol}.NS")` for NSE.
2. Transpose statement DataFrames: columns → `period_end_date` rows; map row labels at wrapper boundary.
3. Call `history(..., auto_adjust=False)` to populate both `close` and `adj_close`.
4. Set `currency` from `info["financialCurrency"]` per ticker (not hardcoded INR).
5. Drop periods where all mapped columns are null (optional, ingestion concern).
6. Let missing row labels and `NaN` cells remain `None`/`NaN` — never coerce to 0.
7. Do not use `get_income_stmt()` camelCase API unless we add a second label-mapping table.

---

## Re-running This Investigation

```bash
.venv/bin/python scripts/investigate_yfinance.py
# Output: scripts/yfinance_probe_output.json
```
