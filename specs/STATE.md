# STATE.md

Planning reference for the Stock Analysis codebase. Describes what exists today
(branch `feature/edgartools`), not what is aspirational.

## 1. Overview

A Python 3.12 data platform for analyzing NSE/BSE (Indian) and US equities. It has
two largely independent halves:

1. **Vendor data ingestion → DuckDB.** A set of vendor API clients (IndianAPI,
   Alpha Vantage, Finnhub) fetch company profiles, financial statements, prices,
   and corporate actions, normalize them into a fixed relational schema, and
   upsert them into a local DuckDB file via `DatabaseManager`. Raw API responses
   are cached to disk as JSON. A small CLI pipeline (`load_from_names`) drives
   this per company name.

2. **SEC filing viewer (the active work).** A FastAPI + Jinja2 web app that, for a
   US ticker, pulls multi-period financial statements from SEC EDGAR via the
   `edgartools` library, builds income/balance/cashflow tables at three
   detail levels ("summary/standard/detailed"), caches the computed bundle
   locally, and serves an interactive HTML page with client-side toggles.

The two halves do **not** currently connect: the EDGAR viewer does not write to
DuckDB, and the DuckDB data is not surfaced in the web app. The screener route is
a placeholder. There is no analytics/factor code yet.

**Why the split exists (open design question, not just unfinished work).** It
mirrors an unresolved tension: a standardized relational schema (the DuckDB half)
makes cross-company analysis easy but discards vendor-specific detail; the raw
edgartools half keeps full fidelity (all XBRL line items, three detail levels) but
isn't queryable across companies. A planner proposing to unify them should treat
this as a real decision to make, not a bug to fix.

**Scope:** personal, single-user, run locally. No auth needed. Production-hardening
is nice-to-have but not required — the developer fixes breakage as it comes up.

## 2. Architecture

```
src/
├── config.py            Central paths, DuckDB location, edgartools cache tuning (env-overridable)
├── api/                  Vendor clients — fetch + parse only, no DB writes
│   ├── base_request_client.py   BaseRequestClient: urllib HTTP + tenacity retry/backoff + JSON parse
│   ├── base_client.py           BaseAPIClient(ABC): abstract fetch_company/financials/
│   │                            balance_sheets/cash_flows/prices/corporate_actions -> pd.DataFrame
│   ├── indianapi/       IndianAPIClient (stock.indianapi.in) + RegistryManager (symbol<->API-name JSON registries)
│   ├── alphavantage/    AlphaVantageClient + parsing.py (field maps schema<-vendor)
│   ├── finnhub/         FinnhubClient (thin/partial) + inline field maps
│   ├── edgartools/      source.py (statement view builder) + cache.py (LRU bundle cache) — NOT a BaseAPIClient
│   ├── finfetch_client.py       Broken stub (bad imports), "finfetch" is a planned vendor
│   └── __init__.py      Exports the 3 working clients + errors
├── database/
│   ├── schema.sql       6 CREATE TABLE statements (source of truth for the relational schema)
│   ├── tables.py        Table names, PRIMARY_KEYS, TABLE_COLUMNS, SCHEMA_DEFAULTS mirrored from schema.sql
│   ├── manager.py       DatabaseManager: connection lifecycle, initialize_schema, upsert_dataframe,
│   │                    load_parquet, company_id resolution, incremental watermark helpers
│   └── init_schema.py   `python -m src.database.init_schema` CLI
├── ingestion/
│   └── load_to_database.py   load_company_to_db / load_to_table: client.fetch_* -> db.upsert_dataframe.
│                             Has a large TODO block; architecture explicitly unfinished.
├── pipelines/
│   └── load_from_names.py    CLI: `python -m src.pipelines.load_from_names <names...> --api {indianapi|alphavantage|finnhub}`
├── models/
│   └── edgartools/html_renderer.py   build_statement_payload: DataFrames -> JSON dict for the template
├── web/
│   ├── app.py           FastAPI app; mounts /static, includes routers, "/" returns a link dict
│   ├── templating.py    Shared Jinja2Templates config
│   └── routes/          statements.py (GET /statements/{ticker}), screener.py (GET /screener, placeholder)
├── templates/           base.html, statements/statement_view.html, screener/index.html
├── static/              css/app.css, js/statement_view.js (client-side statement/level/period toggles)
├── utils/
│   ├── url_cache.py     URLCache: trivial key->JSON-file disk cache under data/raw/<dir>/
│   └── indianapi_parsing.py   Field mapping / date / ratio / dividend parsing helpers for IndianAPI
├── analytics/           EMPTY (only __init__.py) — planned screener/factor SQL
└── models/ (top level)  EMPTY except edgartools/

scripts/     One-off API probe scripts (investigate_indianapi.py, investigate_yfinance.py) + saved JSON output
docs/        indianapi_reference.md, yfinance_reference.md (vendor field notes)
notebooks/   empty (.gitkeep)
tests/       pytest suite (see §4)
data/        raw/ (cached JSON, git-ignored), processed/ (old offline HTML), duckdb/, edgartools_cache/
test_api_clients.py     Stray legacy script at repo root (not under tests/)
```

Key architectural rule (stated in code): **`src/api/` clients only fetch + parse
to DataFrames; all DB writes go through `src/ingestion/` + `DatabaseManager`.**
The `edgartools` module is an exception — it is its own vertical slice (fetch →
cache → render) that bypasses DuckDB entirely.

## 3. Data flow

### Vendor ingestion path (IndianAPI / Alpha Vantage / Finnhub)

1. `load_from_names(names, api)` picks a client, opens `DatabaseManager`, calls
   `db.initialize_schema()`, then loops names calling `load_company_to_db`.
2. `load_company_to_db` calls `client.fetch_company(name)` → single-row DataFrame
   aligned to the `companies` schema (minus `company_id`); upserts it; resolves
   `company_id` by `(symbol, exchange)`; then calls `load_to_table` for
   financials, balance_sheets, cash_flows, prices, corporate_actions.
3. Each `client.fetch_*` method: resolve name → HTTP GET via `BaseRequestClient._request`
   (urllib + tenacity retry) → raw JSON cached to `data/raw/<vendor>/<key>.json`
   via `URLCache` → parsed/field-mapped into a DataFrame whose columns match
   `tables.TABLE_COLUMNS[...]`.
4. `DatabaseManager.upsert_dataframe` aligns columns to the schema, drops unknown
   columns (warns), fills `ingested_at`/`updated_at` and `SCHEMA_DEFAULTS`,
   registers the frame as a staging relation, and runs `INSERT OR REPLACE ... BY NAME`
   (or `ON CONFLICT (company_id) DO UPDATE` for `companies`).
5. DuckDB file: `data/duckdb/indian_stocks.duckdb` (git-ignored). Parquet
   `load_parquet` / `data/raw/<table>/...` partitioning is described in the README
   but ingestion currently goes JSON → DataFrame → DuckDB directly.

- API keys: `INDIAN_API_KEY`, `ALPHAVANTAGE_API_KEY`, `FINNHUB_API_KEY` from
  `.env` (loaded via `python-dotenv`), or constructor arg. Missing key → `ValueError`.
- IndianAPI has a process-level request counter (`get_request_count()`), a
  name/symbol `RegistryManager` backed by `registry_names.json` /
  `registry_field_keys.json` (with write-back), plus a `deprecated.py`.

### SEC EDGAR viewer path

1. `GET /statements/{ticker}?period=annual|quarterly&num_periods=1..40`
   (default annual, 10).
2. `get_all_statement_views(symbol, period, num_periods)`:
   - `load_dotenv()`, require `EDGAR_IDENTITY` env var (else `ValueError`).
   - Point `edgartools` at the local cache dir via `EDGAR_LOCAL_DATA_DIR` and set
     `EDGAR_ALLOW_NETWORK_FALLBACK=True`.
   - Cache lookup: `find_cached_cik` (by ticker in `company_lru.json`) →
     `load_period_bundle`. If miss, resolve `Company(ticker)` (a network call for
     CIK) and retry cache by CIK.
   - On miss: `company.get_filings(form=10-K|10-Q, amendments=False).head(num_periods)`,
     build `XBRLS.from_filings(...)`, then for each statement type × view
     (`summary/standard/detailed`) build a stitched multi-period DataFrame
     (`_build_view_dataframe` uses `determine_optimal_periods` for period
     selection and calls per-filing `to_dataframe(view=...)`).
   - `save_period_bundle` writes each `<statement>_<view>.parquet` + `meta.json`
     (with `latest_filing_date`) under
     `data/edgartools_cache/companies/{cik}/{period}_{num_periods}/`.
   - `touch_company_cache` updates `company_lru.json` and evicts companies beyond
     `EDGARTOOLS_COMPANY_CACHE_SIZE` (default 10) by deleting their cache dirs.
3. `build_statement_payload` serializes the 3 statement types × 3 views into a
   JSON dict (`label`, `level`, `is_total`, `values` per row).
4. `statement_view.html` embeds the payload; `statement_view.js` handles all
   toggling (statement type, detail level, period count) client-side — no
   round-trips.

Cache invalidation: a bundle is stale when `latest_filing_date` is more than
`EDGARTOOLS_CACHE_MAX_AGE_MONTHS` (default 3) old → deleted and refetched.
edgartools' own filing cache also lives under `data/edgartools_cache/` (all
git-ignored).

## 4. Implementation status

**Working**
- DuckDB schema + `DatabaseManager` (upserts, company_id resolution, parquet load,
  watermark helpers). Covered by tests.
- `IndianAPIClient` — all six `fetch_*` methods, caching, registry. Tested.
- `AlphaVantageClient` — all six `fetch_*` (OVERVIEW / INCOME_STATEMENT /
  BALANCE_SHEET / CASH_FLOW / EARNINGS / TIME_SERIES_DAILY / DIVIDENDS / SPLITS).
  Tested.
- edgartools statement fetch + LRU bundle cache + staleness. Tested
  (`test_edgartools_source.py`, `test_edgartools_cache.py`).
- FastAPI app: `/`, `/statements/{ticker}`, `/docs`. Interactive statement page
  with client-side toggles.

**Partial / rough**
- `FinnhubClient` — self-described "thin wrapper / starting point". All `fetch_*`
  exist but `fetch_prices` only returns a QUOTE snapshot; statement parsing relies
  on broad tag-name guessing; no retry beyond base.
- `src/ingestion/load_to_database.py` — works for the happy path but carries an
  explicit TODO block: ingestion logic still partly in the API layer, repeated
  code in `load_company_to_db`, unresolved handling of company_id linkage when
  tables are populated independently, and missing-required-column behavior.
- `_build_view_dataframe` in edgartools `source.py` — works around edgartools
  internals (stitching does not apply view filtering); fragile to library changes.

**Stubbed / not started**
- `src/api/finfetch_client.py` — non-importable stub (`import finfetch`,
  `from base_client import ...`); "finfetch" is a planned market-data vendor,
  referenced in README/pyproject but not a dependency.
- `/screener` route — renders `screener/index.html` placeholder only; no DuckDB
  queries, no HTMX.
- `src/analytics/` — empty. No screeners, ratios, or factor SQL.
- No CLI beyond `init_schema` and `load_from_names` (README roadmap lists
  `init`, `ingest`, `update-prices`, `update-financials`, `screen`).
- Parquet raw-storage layout (`data/raw/{table}/...`) described in README is not
  produced by current ingestion (which caches vendor JSON instead).
- No price/financials ingestion pipeline wired end-to-end beyond
  `load_from_names`.

**Tests** (`pytest`, ~60 test functions): `test_database_manager`,
`test_alphavantage_client`, `test_indianapi_client`, `test_indianapi_parsing`,
`test_finnhub_client` (1 test only), `test_edgartools_source`,
`test_edgartools_cache`. No web/route tests, no Finnhub coverage to speak of,
no ingestion-pipeline tests. `conftest.py` is essentially empty. Legacy
`test_api_clients.py` at repo root is not part of the suite (`testpaths = tests`).

## 5. Key dependencies & external services

**Libraries** (`requirements.txt` / `pyproject.toml`): `duckdb`, `pandas`,
`pyarrow`, `pydantic` (declared, barely used), `tenacity` (retry/backoff),
`fastapi`, `uvicorn[standard]`, `jinja2`, `edgartools` (`import edgar`),
`python-dotenv`. Dev: `pytest`, `ruff`. HTTP uses the stdlib `urllib`, not
`requests`/`httpx`.

**External services / APIs**
- SEC EDGAR via `edgartools` — requires `EDGAR_IDENTITY` (e.g. "Name email").
- IndianAPI.in (`https://stock.indianapi.in`) — `x-api-key`, `INDIAN_API_KEY`.
- Alpha Vantage (`https://www.alphavantage.co`) — `ALPHAVANTAGE_API_KEY`
  (free tier: 25 req/day, 5/min).
- Finnhub (`https://finnhub.io/api/v1`) — `FINNHUB_API_KEY`.
- `finfetch` — planned, not installed. `yfinance` referenced only in
  `scripts/` + `docs/` probes, not a dependency.

All secrets live in `.env` (git-ignored). `.env` currently holds `EDGAR_IDENTITY`
and vendor keys.

## 6. Conventions a new feature should follow

- **Package layout:** vertical modules under `src/<area>/`; each vendor gets its
  own subpackage under `src/api/<vendor>/` with `client.py` + optional
  `parsing.py`. Every dir is a real package with `__init__.py`; public names
  re-exported from the package `__init__`.
- **Separation of concerns:** API clients fetch + parse only, returning
  `pd.DataFrame` shaped to `src/database/tables.TABLE_COLUMNS`. DB writes only via
  `DatabaseManager`. Orchestration in `src/pipelines/`, glue in `src/ingestion/`.
  Don't add DB calls inside `src/api/` (the finfetch stub violating this is a
  known anti-pattern, not a template).
- **Schema is centralized:** `schema.sql` is the source of truth; `tables.py`
  mirrors it (names, PKs, columns, defaults). Change both together. Upserts are
  idempotent (`INSERT OR REPLACE` / `ON CONFLICT`) keyed on the documented PKs.
  `source` column tags provenance; `period_type` is `'annual'|'quarterly'`.
- **Config:** all paths and tunables in `src/config.py`, overridable via env vars
  with `max(1, int(os.environ.get(...)))` clamping. Don't hard-code paths.
- **Naming:** `snake_case` modules/functions, `PascalCase` classes,
  module-private helpers prefixed `_`, `Final` for constants, `from __future__
  import annotations` + PEP 604 unions everywhere, typed signatures, `Literal`
  for enumerated params.
- **Error handling:** one exception subclass per vendor (`IndianAPIError`,
  `AlphaVantageError`, `FinnhubError`, `APIClientError`); raise `ValueError` for
  missing config/keys. HTTP/retry handled centrally in `BaseRequestClient`.
  Pipelines log-and-continue per company (`logger.exception`, then next).
  Caches degrade gracefully (corrupt index/meta → warn, rebuild).
- **Logging:** `logger = logging.getLogger(__name__)` per module; no printing;
  CLIs call `logging.basicConfig`.
- **Caching:** raw vendor JSON → `URLCache` under `data/raw/<vendor>/`; computed
  edgartools bundles → parquet + `meta.json` under `data/edgartools_cache/`;
  atomic writes via `.tmp` + `replace`. Cache dirs are git-ignored.
- **Web:** FastAPI routers per feature in `src/web/routes/`, registered in
  `routes/__init__.py`'s `api_router`. Jinja via shared `templating.templates`.
  Templates extend `base.html`; pass `active_nav`. Prefer client-side JS toggles
  over server round-trips for view state (see `statement_view.js`).
- **CLIs:** `argparse`, `main()` guarded by `if __name__ == "__main__"`, run as
  `python -m src.<pkg>.<mod>`.
- **Tests:** `pytest`, files `tests/test_<module>.py`, plain `def test_*`
  functions (no classes), `pytest.approx` for floats, vendor responses stubbed
  from fixtures/sample JSON (`tests/data/`). `pythonpath = ["."]`.

## 7. Known limitations / technical debt

- **The two halves are disconnected** — by open question, not oversight (see
  Overview). EDGAR data never lands in DuckDB; DuckDB data never reaches the web
  UI. A feature spanning both forces the standardize-vs-preserve-detail decision.
- **`load_to_database.py` architecture is explicitly unfinished** (see its TODO
  block): company_id linkage across independently-fetched tables, dedup of
  `load_company_to_db`, missing-column policy all unresolved. Don't build heavily
  on the current ingestion shape without expecting to refactor it.
- **Dead code from exploration**, slated for a cleanup PR (low priority):
  `finfetch_client.py` (broken imports, references an uninstalled library, yet
  README/pyproject still advertise finfetch and `'finfetch'` is the schema
  `source` default), `test_api_clients.py` at repo root,
  `src/api/indianapi/deprecated.py` + `probe_api.py`, the stale
  `sec_edgar_financials` `.pyc` + `data/raw/sec-edgar-financials/`, empty
  `notebooks/`, superseded `data/processed/*.html`.
- **Finnhub client is not production-ready** — snapshot-only prices, guess-based
  statement field extraction, ~1 test.
- **edgartools view builder depends on library internals**
  (`edgar.xbrl.stitching.periods.determine_optimal_periods`, per-filing
  `to_dataframe(view=...)`); an `edgartools` upgrade can break it silently.
- **No web-layer tests**; no rate-limit handling for the SEC beyond edgartools
  defaults. `/statements` triggers live SEC fetches on cache miss (can be slow;
  first hit resolves CIK over the network). (Lack of auth is intentional —
  local single-user.)
- **Alpha Vantage free-tier limits** (25/day) make bulk ingestion impractical
  without caching already-fetched responses (which exist under `data/raw/`).
- **Currency assumptions:** schema defaults financial currency to `INR`;
  US tickers via Alpha Vantage/edgartools are USD — no normalization layer.
- No migrations: schema changes require manual DuckDB rebuild
  (`init_schema` only does `CREATE TABLE IF NOT EXISTS`).
