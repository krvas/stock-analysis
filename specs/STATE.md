# STATE.md

What exists today (not vision). Product intent: `specs/vision.md`.
Adjustments/statement-model redesign: `specs/adjustments_architecture.md` —
phase 1 (cache + `Statement`) implemented; phases 2–5 not.
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
src/pipelines/             CLIs (load_from_names, calc_residual_report)
src/database/              schema.sql + tables.py; wizard.sql + wizard_tables.py
                           manager.py (BaseDatabaseManager, DatabaseManager)
                           wizard_manager.py, adjustments.py
src/models/statement.py    Statement / StatementSet / get_row_id
                           (pure domain: pandas only, no I/O)
src/models/calc_residuals.py  calc_residuals (calc-linkbase residuals; pure)
src/models/table.py        Table / ColumnSpec / LinkedGroupSpec  (FE↔BE contract)
src/models/edgartools/html_renderer.py   DataFrames → Table.serialize() payload
src/web/app.py             FastAPI; / → {statements, wizard, screener, docs}
src/web/wizard_registry.py page/sub-page identity (only place)
src/web/routes/            statements.py, wizard.py, screener.py
src/web/routes/wizard_pages/  context builders (adjustments.py)
src/templates/wizard/      landing, base_subpage, _nav, not_implemented,
                           {page}/{subpage}.html
src/templates/macros/line_item_table.html
src/static/js/             api_client.js (only fetch() home; wizard save posts)
                           components/table_model.js, linked_groups.js,
                           table_view.js, generic_input.js, table_wiring.js
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
  A leading underscore means internal to that module only, never imported
  elsewhere — a helper another module needs to import must not have one.
- CLIs: `python -m src.<pkg>.<mod>`.
- Logging: `logger = logging.getLogger(__name__)` per module; no printing;
  CLIs call `logging.basicConfig`.
- Caching: Vendor data should almost always be cached. The caching strategy is
  determined by the developer. For `edgartools`, a company LRU parquet cache
  exists (§4).

## 4. Paths that matter

**Vendor ingest.** `load_from_names` → `load_company_to_db` → `fetch_*` (HTTP +
`URLCache` JSON under `data/raw/<vendor>/`) → upsert. Keys:
`INDIAN_API_KEY`, `ALPHAVANTAGE_API_KEY`, `FINNHUB_API_KEY`. Ingestion module
has an explicit unfinished TODO; don’t extend its shape without expecting a
refactor. Finnhub is thin (quote snapshot, guessy statements).

**EDGAR.** `GET /statements/{ticker}?period=annual|quarterly&num_periods=1..64`
(default annual, 10; clamped to `MAX_CACHE_*` and to cached periods). Needs
`EDGAR_IDENTITY`. 3 statements (income, balance, cashflow) × 3 views
(summary, standard, detailed). edgartools' own HTTP cache (filing
documents): once the `_cache`/`_tcache` directories under
`data/edgartools_cache` are over `EDGARTOOLS_HTTP_CACHE_MAX_MB` (default
300), setup clears them completely with edgartools' own `clear_cache` (which
only touches `_cache`/`_tcache`, never our `companies/` bundles).

`load_statement_set(ticker, period) -> StatementSet` (`source.py`) is the
only entry point. Cache key `(cik, period)`, no `num_periods`:
`companies/{cik}/{period}/{income,balance,cashflow}.parquet` +
`{statement}_calc.parquet` + `meta.json` (`schema_version`, `period`,
`latest_filing_date`); `read_period_bundle` returns a `CachedPeriodBundle` whose `bundle` is `{statement:
StatementFrames(frame, calc_edges)}`, and a missing calc file makes the
bundle unusable. Builds from up
to `MAX_CACHE_YEARS` (16) 10-Ks or `MAX_CACHE_QUARTERS` (64) 10-Qs: XBRLS only
picks filings/periods (`determine_optimal_periods`); each filing gets
`to_dataframe(view="detailed", presentation=False)` per statement (the stored
frame) plus `view="standard"` only to set `in_standard`: standard rows are an
ordered subsequence of detailed rows, matched by `_align` (the same walk
`_raw_items` uses against `get_raw_data(view="detailed")`); on failure `Statement`
defaults it to `not dimension or not is_breakdown`. The aligned raw items
(fetched once per filing statement) give `dimension_key` and replace
`weight`: edgartools' frame weight comes from the concept's first fact and can
be another role's calc tree, the raw item's is this role's (same node as
`parent_concept`); dimensional rows take their concept's role weight. If
alignment fails, edgartools' weight is kept. Rows
matched across filings by `get_row_id`; metadata from the newest filing a
row appears in, except `weight` = newest non-NaN across filings. Values
stored with **raw** XBRL signs. Because filers restructure calc trees, those
`parent_concept` / `weight` columns are newest-filing metadata only:
`Statement.calc_edges` (long frame `period, concept, parent_concept, weight`,
stored as `{statement}_calc.parquet`) gives each period every arc of the
statement role's calc tree (`xbrl.find_statement` → `calculation_trees`, no
cross-role fallback) of the filing that period's values came from; calc code
must use it. Without stored edges, `Statement` broadcasts the frame's own
tree to every period. `Statement.children(row_id, period)` returns the
non-dimensional child rows in that period's edges, `weight` = edge weight.
Rebuilt on `schema_version` mismatch (`CACHE_SCHEMA_VERSION`) or
missing/corrupt files. A bundle whose `latest_filing_date` is older than
`EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS` (12) /
`EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS` (3) (quarterly: newer of latest
10-Q and latest 10-K, so a year-end 10-K keeps it fresh) is stale
(`read_period_bundle` returns it with `stale=True` and keeps it on disk): `load_statement_set` then fetches the filing list and
rebuilds only if SEC has a newer filing (freshness date ≠ stored); otherwise
it serves the cached bundle. Fresh bundles make no SEC request. Company LRU
size `EDGARTOOLS_COMPANY_CACHE_SIZE` (10), index `company_lru.json`. Pinned
tickers (`set_pinned_tickers`, stored in `company_lru.json`) are exempt from
LRU eviction and don't count toward the size; staleness still applies.

Views are projections: `Statement.project(view, periods)` — summary =
non-dimensional rows, standard = `in_standard` (edgartools' standard-view
membership, read from its standard frame at cache build), detailed = all;
`preferred_sign` applied only here. `html_renderer.py` projects each
statement to every view over `periods[:num_periods]`. Payload is nested Table JSON;
`statement_view.js` toggles type/level and balance-sheet fund-flow
client-side.

`get_row_id` (only place ids are formed): `concept`, plus
`|Axis=member` for every axis of a dimensional row (sorted by axis, axis
prefix stripped, member QName kept), `#n` for repeats within one filing.
`calc_residuals(statement)` (`src/models/calc_residuals.py`): per period,
`reported(parent) − Σ weight·child` on that period's own `calc_edges` (raw
signs; edge weights; first non-dimensional row per concept). NaN child values
count 0 (`n_nan_children`); calc children with no non-dimensional row are
counted in `n_missing_children`.
Expected 0 on real filings (data test: AAPL/MU/SNDK all 0); the old diluted
shares residual is gone (edges come from the statement role only, not the
EPS-note role).
`calc_residual_report` CLI runs it over the cache (read-only).

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
builder: `load_statement_set(...).income.project("detailed")` over the newest
2 periods, `standard_concept` in `OPERATING_EXPENSES`, `Table` (rows still
keyed by `standard_concept` until row-id unification, phase 2)
with period cols + input `capitalize` (bool) + `years` (number). Saves: POSTs
to `/wizard/{ticker}/{page_slug}/{subpage_slug}` →
`wizard_pages/adjustments_post.py::opex_to_capex_post` →
`WizardDatabaseManager.upsert_adjustment_preferences` (writes
`adjustment_preferences`). Saved prefs are read back and pre-filled into the
`Table` on load via
`wizard_pages/adjustments_context.py::_apply_saved_opex_to_capex_preferences`.
No restatement (prefs only, not applied to displayed numbers).

**wizard.duckdb** `adjustment_preferences`: PK `adjustment_id`, unique
`(ticker, exchange, adjustment_type, base_concept)`. Types intended:
`opex_to_capex` | `maintenance_capex` | `assets_in_use`; `value` is years or
%. Tested; written/read by `adjustments_post.py` / `adjustments_context.py`
for `opex_to_capex` — other adjustment types still unused by routes.

## 5. Table / TableModel contract (`src/models/table.py`, `components/table_model.js`)

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
  periods. Metadata = `STATEMENT_VIEW_METADATA_COLUMNS`: `label, concept,
  standard_concept, preferred_sign, level, is_total, is_abstract` plus every
  `Statement` column from `statement.py` (`STATEMENT_METADATA_COLUMNS`, incl.
  `row_id`).
- Missing input cols → `null`. NaN → `null`. Bad spec → `TableSerializationError`.
- **Model** (`components/table_model.js`): receives table data
  (`fromSerialized`), owns cell state (`getCell`/`setCell`/`subscribe`/
  `serialize`). No DOM. Linked-group math runs on `setCell` via
  `LINKED_GROUP_HANDLERS` imported from `components/linked_groups.js`.
  Python only *describes* `linked_groups` in the payload; it does not
  compute them.
- **View** (`components/table_view.js`): `render_table(container, table)`.
  `container` is the `<table>` element. Paints headers, labels, static cells,
  link cells, and empty input slots (`data-input-slot`, `data-row-id`,
  `data-col-id`, `data-dtype`). No event handlers.
- **Input controller** (`components/generic_input.js`): `GenericInput` is the
  only module that creates an `<input>` and attaches `input`/`change`
  listeners; `subscribe` receives the coerced value; `set()` writes the
  element and skips notify when unchanged.
- **Wiring** (`components/table_wiring.js`): wizard hydration — JSON →
  `TableModel.fromSerialized` → `render_table` → one `GenericInput` per slot;
  `input.subscribe` → `model.setCell`; `model.subscribe` → `input.set`.
  Must not read `input.value` / `input.checked`. Save posts
  `model.serialize()`. Currently just `adjustments/opex-to-capex` (see §4),
  not every wizard sub-page. Convention: frontend module files that run
  wizard-page side effects wrap all their top-level execution in a single
  `main()` (or similarly named) function invoked once at the bottom, rather
  than having multiple bare top-level statements.
- **Statements** (`statement_view.js`): calls `render_table` with the nested
  statement view object or a fund-flow-shaped plain object (latest, previous,
  change columns) built client-side; `staticPeriodColumnIds` is local to
  that file. Page `<select>` listeners stay there (controls, not table-cell
  inputs).
- `Table.serialize()` / `TableModel.fromSerialized()` (receive direction) and
  `TableModel.serialize()` (send direction) are **intentionally asymmetric**,
  not two encodings of the same shape. Receive: full `{columns,
  linked_groups, rows}`, every `kind`. Send: `{columns, rows}`, only
  `kind === "input"` columns and only those columns' cell values — no
  `linked_groups`, because the backend only ever needs what the user edited,
  not the full read-side payload it already computed and sent down. Do not
  "fix" `TableModel.serialize()` to match `Table.serialize()`'s shape, and do
  not expect `TableModel.serialize(TableModel.fromSerialized(x))` to
  round-trip `x`.
- Wizard table state flows model → view slots → `GenericInput` via
  `table_wiring.js`; shared component files must not scrape input DOM for
  save payloads and must not hold per-sub-page field-shaping logic. Generalizes
  the "registry = identity, builders = data" split in §4.
- `find_row_id(base_concept)` / `set_cell(column_id, row_id, value)`: write
  helpers used to inject saved wizard prefs into a `Table` before
  `serialize()`. `find_row_id` maps a stored pref key to a row id (exact match
  on `row_id_col`, else exact match on `standard_concept`); `set_cell` mutates
  the underlying DataFrame (adding the column if missing). `Table` is not
  read-only.

Embed: `{% table(id, data) %}` → JSON script + empty `<table>`;
`base_subpage.html` loads `components/table_wiring.js` to hydrate wizard
tables. Statements nest the same object under `statements[type][view]` and
use `statement_view.js` → `render_table`. Tests: `tests/test_table.py`.

## 6. Status (short)

Working: vendor DuckDB + IndianAPI/AlphaVantage; edgartools fetch/cache;
`/statements`; wizard shell + opex table; Table used by statements + opex;
`TableModel` + `linked_groups` + view slots + `GenericInput` subscriptions in
`table_wiring.js` wired for opex-to-capex (receive, render, live edits,
linked-group math); prefs store (no UI).

Partial: opex (save/prefill for `adjustments/opex-to-capex` only; no
restatement); Finnhub; `load_to_database.py`.

NYI: every other wizard sub-page; wizard UI ↔ DuckDB; screener; analytics;
finfetch.

Tests cover clients, DBs, edgartools, Table, wizard DB. No web tests. Cache
miss hits live SEC. `pytest -m data` (deselected by default)
runs the calc-residual check on real filings for the tickers in the gitignored
`tests/data_test_tickers.txt` (pinned in the company LRU, loaded through the
app cache).

## 7. Debt agents should not paper over

- No schema migrations (`CREATE TABLE IF NOT EXISTS` only).
- Schema currency default `INR`; US data is USD — no FX layer.
- Alpha Vantage free tier 25/day.
- Dead exploration: `finfetch_client.py`, root `test_api_clients.py`,
  indianapi `deprecated.py` / `probe_api.py` — not patterns to copy.
