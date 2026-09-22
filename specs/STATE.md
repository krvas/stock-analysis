# STATE.md

What exists today (not vision). Product intent: `specs/vision.md`.
Audience: planning and coding agents — prefer this file over guessing layout.

Python 3.12, pandas, FastAPI + Jinja SSR, vanilla JS (no frontend libs). Local
single-user; no auth. Keep UI simple while building features.

## 1. Three disconnected slices (do not “unify” as a bugfix)

| Slice | Role | Store |
| --- | --- | --- |
| Vendor ingest | IndianAPI / Alpha Vantage / Finnhub → schema-shaped DataFrames | `data/duckdb/indian_stocks.duckdb` |
| EDGAR viewer | US 10-K/10-Q, 3 statements × `summary\|standard\|detailed` | parquet under `data/edgartools_cache/` |
| Wizard (active work) | Per-ticker pages/sub-pages; user processing choices | `data/duckdb/wizard.duckdb` (prefs; UI not wired) |

They do not share data. Standardized DuckDB is easy to query across companies
but loses XBRL detail; edgartools keeps full line items but is not
cross-company. The wizard sits on edgartools and should persist **rules**
(what to capitalize, years/%), not restated numbers, so refreshed filings
re-apply. Unifying slices is an explicit design decision.

`/screener` and `src/analytics/` are empty placeholders.

**Why the split exists (open design question, not just unfinished work).** It
mirrors an unresolved tension: a standardized relational schema (the DuckDB half)
makes cross-company analysis easy but discards vendor-specific detail; the raw
edgartools half keeps full fidelity (all XBRL line items, three detail levels) but
isn't queryable across companies. A planner proposing to unify them should treat
this as a real decision to make, not a bug to fix.

## 2. Layout

```
src/config.py              paths + cache tunables (env)
src/api/<vendor>/          fetch+parse only → DataFrame. No DB writes.
src/api/edgartools/        source.py, cache.py, standard_terms.py  (not BaseAPIClient)
src/ingestion/             vendor DataFrame → DatabaseManager
src/pipelines/             CLIs (load_from_names)
src/database/              schema.sql + tables.py; wizard.sql + wizard_tables.py
                           manager.py (BaseDatabaseManager, DatabaseManager)
                           wizard_manager.py, adjustments.py
src/models/table.py        Table / ColumnSpec / LinkedGroupSpec  (FE↔BE contract)
src/models/edgartools/html_renderer.py   DataFrames → Table.serialize() payload
src/web/app.py             FastAPI; / → {statements, wizard, screener, docs}
src/web/wizard_registry.py page/sub-page identity (only place)
src/web/routes/            statements.py, wizard.py, screener.py
src/web/routes/wizard_pages/  context builders (adjustments.py)
src/templates/wizard/      landing, base_subpage, _nav, not_implemented,
                           {page}/{subpage}.html
src/templates/macros/line_item_table.html
src/static/js/             api_client.js (only fetch() home; wizard stub)
                           tables.js, table_model.js, line_item_tables.js,
                           statement_view.js, utils.js
tests/                     pytest; no HTTP/route tests
```

`finfetch_client.py` is a broken stub; ignore as a template.

## 3. Hard rules

- `src/api/` returns DataFrames. Vendor writes only via `DatabaseManager`.
  Wizard prefs only via `WizardDatabaseManager` / `adjustments.py`.
- Schema truth: `schema.sql` / `wizard.sql`; Python mirrors must change with them.
- Config only in `src/config.py`. Routers in `src/web/routes/`, registered in
  `routes/__init__.py`. Templates extend `base.html`; pass `active_nav`.
- New financial tables: pandas → `Table` → `serialize()` → `{columns,
  linked_groups, rows}`. Do not invent another payload or pass DataFrame dicts
  to the browser. This also applies to the frontend, with the `TableModel`
  schema.
- New `fetch()` only in `api_client.js`.
- Naming: `snake_case` / `PascalCase` / `_private`; `from __future__ import
  annotations`; typed; `Literal` for enums. Tests: `tests/test_*.py`, `def test_*`.
- CLIs: `python -m src.<pkg>.<mod>`.
- Logging: `logger = logging.getLogger(__name__)` per module; no printing;
  CLIs call `logging.basicConfig`.
- Caching: Vendor data should almost always be cached. The caching strategy is
  determined by the developer. For `edgartools`, LRU cache has already been
  implemented.

## 4. Paths that matter

**Vendor ingest.** `load_from_names` → `load_company_to_db` → `fetch_*` (HTTP +
`URLCache` JSON under `data/raw/<vendor>/`) → upsert. Keys:
`INDIAN_API_KEY`, `ALPHAVANTAGE_API_KEY`, `FINNHUB_API_KEY`. Ingestion module
has an explicit unfinished TODO; don’t extend its shape without expecting a
refactor. Finnhub is thin (quote snapshot, guessy statements).

**EDGAR.** `GET /statements/{ticker}?period=annual|quarterly&num_periods=1..40`
(default annual, 10). Needs `EDGAR_IDENTITY`.
It will load financial statements from edgartools - 3 statements (income
statement, balance sheet and cash flow) and 3 different levels of granularity
(summary, standard, detailed).
`get_all_statement_views` LRU-caches a full 3×3 bundle
(`companies/{cik}/{period}_{num_periods}/*.parquet` + `meta.json`). Stale if
`latest_filing_date` older than
`EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS` (12) or
`EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS` (3). Company LRU size
`EDGARTOOLS_COMPANY_CACHE_SIZE` (10). `_build_view_dataframe` depends on
edgartools internals (`determine_optimal_periods`, per-filing
`to_dataframe(view=)`). Payload is nested Table JSON; `statement_view.js`
toggles type/level and balance-sheet fund-flow client-side.

`get_statement_views(...)` still loads the **full** bundle then indexes one
statement — wizard opex pays for all three statements on a cold cache.

**Wizard.**

- `GET /wizard?ticker=` → `/wizard/{TICKER}` landing (form + grouped pages)
- `/wizard/{t}/{page}` → first sub-page by `order`
- `/wizard/{t}/{page}/{subpage}?period=annual` — unknown slug → 404

Identity: frozen `Page` / `SubPage` in `WIZARD_PAGES`. Groups: `business`,
`people`, `price`, `red_flags`. `context_builder(ticker, period) -> dict`
(default `{}`). Template `wizard/{page}/{subpage}.html` or
`not_implemented.html`. Extend `base_subpage.html` (tabs, breadcrumb, blocks
`subpage_content` / `computed_values` / `human_input` / `source_trace`).

**Add a sub-page:** (1) `SubPage` on the right `Page` in the registry, (2)
template under `templates/wizard/<page>/<subpage>.html`, (3) optional builder
in `wizard_pages/` — registry = identity, builders = data. Do not add
per-sub-page routes.

Slots match `vision.md`; **only `adjustments/opex-to-capex` has UI.** That
builder: detailed income, `standard_concept` in `OPERATING_EXPENSES`, `Table`
with period cols + input `capitalize` (bool) + `years` (number). No save, no
restatement, inputs not submitted.

**wizard.duckdb** `adjustment_preferences`: PK `adjustment_id`, unique
`(ticker, exchange, adjustment_type, base_concept)`. Types intended:
`opex_to_capex` | `maintenance_capex` | `assets_in_use`; `value` is years or
%. Tested; wizard routes do not call it.

## 5. Table contract (`src/models/table.py`)

Column-schema JSON so statement views and wizard tables share one renderer.

```
serialize() → {
  columns: [{id, label, kind, dtype, format?, linked_group?}],
  linked_groups: {name: {type: "pct_of_base", base_col, pct_col, value_col}},
  rows: [{id, label, level, is_total, parent_id, cells: {colId: value}}]
}
```

- `kind`: `static` | `input` | `link`. `dtype`: `number` | `string` | `boolean`.
- number `format`: `financial` | `percent` | `integer`. Links: `dtype=string`,
  cell `{text, href}`.
- `statement_table_from_dataframe(df)`: non-metadata cols → static financial
  periods. Metadata: `label, concept, standard_concept, preferred_sign, level,
  is_total, is_abstract`.
- Missing input cols → `null`. NaN → `null`. Bad spec → `TableSerializationError`.
- Python only *describes* `linked_groups`; math is `TableModel` (`table_model.js`),
  **not wired to DOM yet** — inputs are display-only.

Embed: `{% table(id, data) %}` → JSON script + empty `<table>`;
`line_item_tables.js` → `renderLineItemPeriodsTable`. Statements nest the same
object under `statements[type][view]`. Tests: `tests/test_table.py`.

## 6. Status (short)

Working: vendor DuckDB + IndianAPI/AlphaVantage; edgartools fetch/cache;
`/statements`; wizard shell + opex table; Table used by statements + opex;
prefs store (no UI).

Partial: opex (no apply/persist); Finnhub; `load_to_database.py`;
`TableModel` unused.

NYI: every other wizard sub-page; wizard UI ↔ DuckDB; screener; analytics;
finfetch; README parquet layout.

Tests cover clients, DBs, edgartools, Table, wizard DB. No web tests. Cache
miss hits live SEC.

## 7. Debt agents should not paper over

- No schema migrations (`CREATE TABLE IF NOT EXISTS` only).
- Schema currency default `INR`; US data is USD — no FX layer.
- Alpha Vantage free tier 25/day.
- Dead exploration: `finfetch_client.py`, root `test_api_clients.py`,
  indianapi `deprecated.py` / `probe_api.py` — not patterns to copy.
