# STATE.md

What exists today (not vision). Product intent: `specs/vision.md`.
Adjustments/statement-model redesign: `specs/adjustments_architecture.md` —
phases 1–2 (cache + `Statement`; row-id unification) implemented; the
adjustment engine (`src/adjustments`, types `opex_to_capex`,
`owner_earnings` and `assets_in_use`) exists and the statement pages,
Balance Sheet Size and Fund Flow consume it through the Basis Setting.
Audience: planning and coding agents — prefer this file over guessing layout.

Python 3.12, pandas, FastAPI + Jinja SSR, vanilla JS (no frontend libs). Local
single-user; no auth. Keep UI simple while building features.

Under development, not deployed: there is no production data to preserve.
The databases (`indian_stocks.duckdb`, `wizard.duckdb` in `data/duckdb/`, see
`DEFAULT_DB_PATH` / `DEFAULT_WIZARD_DB_PATH` in `src/config.py`) can be deleted
and rebuilt (`src.database.init_schema`, `src.database.init_wizard_schema`).

## 1. Three disconnected slices (do not “unify” as a bugfix)

| Slice | Role | Store |
| --- | --- | --- |
| Vendor ingest | IndianAPI / Alpha Vantage / Finnhub → schema-shaped DataFrames | `data/duckdb/indian_stocks.duckdb` |
| EDGAR viewer | US 10-K/10-Q, 3 statements × `summary\|standard\|detailed` | parquet under `data/edgartools_cache/` |
| Wizard (active work) | Per-ticker pages/sub-pages; user processing choices | `data/duckdb/wizard.duckdb` (prefs; opex-to-capex only) |

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
src/pipelines/             CLIs (load_from_names, calc_residual_report,
                           convert_adjustment_pref_keys)
src/database/              schema.sql + tables.py; wizard.sql + wizard_tables.py
                           manager.py (BaseDatabaseManager, DatabaseManager)
                           wizard_manager.py (WizardDatabaseManager: prefs I/O)
src/models/statement.py    Statement / StatementSet / get_row_id
                           (pure domain: pandas only, no I/O)
src/models/calc_residuals.py  calc_residuals (calc-linkbase residuals; pure)
src/models/balance_leaves.py  balance_leaves (balance-sheet leaves, side, equity
                           flag, effective calc weight; pure)
src/models/table.py        Table / ColumnSpec / LinkedGroupSpec  (FE↔BE contract)
src/web/app.py             FastAPI; / → {statements, wizard, screener, docs}
src/web/settings.py        Settings registry + pure rules (resolve,
                           apply_submission, build_drawer); no HTTP
src/web/wizard_registry.py wizard page/sub-page identity (only place)
src/web/statements_registry.py  statement page identity (income, balance,
                           cashflow)
src/web/adjusted_statements.py  load_adjusted (staged), load_for_basis
src/web/routes/            statements.py, wizard.py, screener.py,
                           settings.py (cookies, POST /settings,
                           render_with_settings, NavContext)
src/web/routes/wizard_pages/  business_understanding.py, adjustments_context.py,
                           owner_earnings.py, assets_in_use.py (builders),
                           adjustments_post.py (POST handler)
src/templates/shared/      _page_nav (nav + gear), _settings_drawer,
                           _adjustments_note
src/templates/wizard/      landing, base_subpage, not_implemented,
                           {page}/{subpage}.html
src/templates/statements/statement_view.html
src/templates/macros/line_item_table.html
src/static/js/             api_client.js (only fetch() home; wizard save posts)
                           components/table_model.js, linked_groups.js,
                           table_view.js, generic_input.js, table_wiring.js
                           settings_drawer.js, utils.js
tests/                     pytest; pure seams (Settings, builders);
                           test_settings_routes.py over HTTP (TestClient)
```

`finfetch_client.py` is a broken stub; ignore as a template.

## 3. Hard rules

- `src/api/` returns DataFrames. Vendor writes only via `DatabaseManager`.
  Wizard prefs only via `WizardDatabaseManager` (`wizard_manager.py`).
- Row ids only via `get_row_id` (§4); never re-derive ids elsewhere.
- Schema truth: `schema.sql` / `wizard.sql`; Python mirrors must change with them.
- No migrations, backfills, or legacy-format fallbacks (pre-deployment): edit
  the schema/code directly and reset the DB.
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

**EDGAR.** `GET /statements/{ticker}/{income|balance|cashflow}` (bare
`/statements/{ticker}` → 307 to `income`; unknown slug → 404). Period type,
number of periods, View and Basis come from Settings (§4 Settings), never the
URL; the period count is clamped to `MAX_CACHE_*` and to cached periods.
Needs `EDGAR_IDENTITY`. 3 statements (income, balance, cashflow) × 3 views
(summary, standard, detailed). edgartools' own HTTP cache (filing
documents): once the `_cache`/`_tcache` directories under
`data/edgartools_cache` are over `EDGARTOOLS_HTTP_CACHE_MAX_MB` (default
300), setup clears them completely with edgartools' own `clear_cache` (which
only touches `_cache`/`_tcache`, never our `companies/` bundles).

`load_statement_set(ticker, period) -> StatementSet` (`source.py`) is the
only entry point. Cache key `(cik, period)`, no `num_periods`:
`companies/{cik}/{period}/{income,balance,cashflow}.parquet` +
`{statement}_calc.parquet` + `meta.json` (`schema_version`, `period`,
`latest_filing_date`); `read_cache_entry` returns a `CachedStatementSet` (a `StatementSet` plus
`latest_filing_date` and a `stale` property); a missing calc file, or a frame
`Statement` rejects, makes the bundle unusable. Builds from up
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
(`read_cache_entry` returns it with `stale=True` and keeps it on disk): `load_statement_set` then fetches the filing list and
rebuilds only if SEC has a newer filing (freshness date ≠ stored); otherwise
it serves the cached bundle. Fresh bundles make no SEC request. Company LRU
size `EDGARTOOLS_COMPANY_CACHE_SIZE` (10), index `company_lru.json`. Pinned
tickers (`set_pinned_tickers`, stored in `company_lru.json`) are exempt from
LRU eviction and don't count toward the size; staleness still applies.

Views are projections: `Statement.project(view, periods)` — summary =
non-dimensional rows, standard = `in_standard` (edgartools' standard-view
membership, read from its standard frame at cache build), detailed = all;
`preferred_sign` applied only here. `routes/statements.py::statement_context`
projects the page's one statement in the resolved View over
`settings.recent_periods(...)` on the resolved Basis (`load_for_basis`) into
one `Table` payload; nothing switches client-side.

`get_row_id` (`statement.py`; only place ids are formed): `concept`, plus
`|Axis=member` for every axis of a dimensional row (axis local name, sorted;
member QName kept), `#n` (n ≥ 2) for repeats within one filing. Stored in the
cache's `row_id` column; `Table` rows (§5) and opex-to-capex pref keys use it
verbatim.
`calc_residuals(statement)` (`src/models/calc_residuals.py`): per period,
`reported(parent) − Σ weight·child` on that period's own `calc_edges` (raw
signs; edge weights; first non-dimensional row per concept). NaN child values
count 0 (`n_nan_children`); calc children with no non-dimensional row are
counted in `n_missing_children`. `rounding` bounds what rounding each value to
the summation's reporting unit (largest power of ten up to 1e6 dividing that
parent's and its children's values in the period, so per-share values in the
same tree don't set the dollars' unit) can add: `unit / 2 · (1 + Σ|w|)`. The residual report and data
test count a residual within it as zero.
Expected 0 on real filings (data test: AAPL/MU/SNDK all 0); the old diluted
shares residual is gone (edges come from the statement role only, not the
EPS-note role).
`calc_residual_report` CLI runs it over the cache (read-only).

**Wizard.**

- `GET /wizard?ticker=` → `/wizard/{TICKER}` landing (form + grouped pages)
- `/wizard/{t}/{page}` → first sub-page by `order`
- `/wizard/{t}/{page}/{subpage}` — unknown slug → 404; no query params

Identity: frozen `Page` / `SubPage` in `WIZARD_PAGES`. Groups: `business`,
`people`, `price`, `red_flags`. `context_builder(ticker, settings) -> dict`
(default `{}`), `settings` = the resolved `Settings`. Template
`wizard/{page}/{subpage}.html` or `not_implemented.html`. Extend
`base_subpage.html` (shared nav, breadcrumb, blocks `subpage_content` /
`computed_values` / `human_input` / `source_trace`).

**Add a sub-page:** (1) `SubPage` on the right `Page` in the registry, with
its `settings=SettingsDecl(...)` if it uses Sub-page Settings or greys out a
Global one, (2) template under `templates/wizard/<page>/<subpage>.html`, (3)
optional builder in `wizard_pages/` — registry = identity, builders = data.
Do not add per-sub-page routes.

Sub-pages with UI: `business-understanding/` `one-line-answers` (AI answers;
View detailed adds justification + source), `balance-sheet-size` (annual
treemaps at `current_period`, `items_per_side` per side, on the chosen
Basis), `fund-flow` (balance sheet at `current_period` vs `previous_period`
+ change column, server-built by `fund_flow_table`; notice when the offsets
clamp to one period); `adjustments/` `opex-to-capex`, `owner-earnings` and
`assets-in-use` (each shows the stage before its own adjustment, over
`num_periods`; assets-in-use always loads annual and greys out period and
view). The `assets_in_use` type declares `APPLIES_BY_DEFAULT`, so
`specs.from_prefs` emits it with empty params even when nothing is saved:
every adjusted balance sheet carries the Gross and Net Assets in Use memo
rows. Memo rows (no calc parent) carry `MEMO_TAG` (`adjustments/base.py`):
the statements page shows them, `fund_flow_table` leaves them out.
The opex-to-capex builder: staged `income.project("detailed")` over
`settings.recent_periods(...)`, `standard_concept` in `OPERATING_EXPENSES` (selection only),
`Table` keyed by `row_id` (from `get_row_id`) with period cols + input
`capitalize` (bool) + `years` (number). The posted row `id` is that row id
and is stored verbatim in `adjustment_preferences.base_concept` (column name
kept); prefill matches it exactly via `find_row_id`.
Legacy prefs keyed by `standard_concept`/`concept` are re-keyed to row ids
by the one-off `convert_adjustment_pref_keys` CLI (`--dry-run`; reads each
ticker's `Statement`; skips keys already row ids; ambiguous/conflicting keys
logged and left; writes via
`WizardDatabaseManager.rename_adjustment_preference_keys`). Saves: POSTs
to `/wizard/{ticker}/{page_slug}/{subpage_slug}` →
`wizard_pages/adjustments_post.py::opex_to_capex_post` →
`WizardDatabaseManager.upsert_adjustment_preferences` (writes
`adjustment_preferences`). Saved prefs are read back and pre-filled into the
`Table` on load via
`wizard_pages/adjustments_context.py::_apply_saved_opex_to_capex_preferences`.
The adjustment engine (`src/adjustments`) restates statements from saved
prefs; pages read it through `src/web/adjusted_statements.py`.
`apply_adjustments(base, specs, until=None)` returns an `AdjustmentRun`
(`adjustments/base.py`): `statements`, the `applied` specs, and `skipped`
(`SkippedSpec(spec, reason)`). A spec is skipped when its type raises
`KeyError`/`ValueError` or its `AdjustmentResult` changes nothing; a type
reports a part it could not apply in `AdjustmentResult.skipped` (opex-to-capex:
a saved row id missing from the filing) and the part that did in
`AdjustmentResult.applied_params`, so a partly applied spec is in `applied`
narrowed to that part and in `skipped` once per missing part.
`load_for_basis` returns the run; `specs.describe(run)` builds the
`_adjustments_note` context, `{"applied": [...], "skipped": [...]}`, which
says "Adjusted for" only for what applied (counts included) and names each
skipped part by its type's `LABEL` and reason, with no count. A type's `describe` returning None leaves its spec out of both.

**Settings** (`src/web/settings.py`, `src/web/routes/settings.py`). A Setting
is a display choice (CONTEXT.md). `SETTINGS` defines each once (id, label,
`Option(value, label)` choices or int range, default; `instant` = View only,
submits on change).
Global: `period`, `num_periods`, `view`. Sub-page: `basis`,
`current_period`, `previous_period` (offsets from the latest period),
`items_per_side`. Every `SubPage` and `StatementPage` carries a
`SettingsDecl(uses=..., cannot_honour={global_id: reason})` (identity, in the
registries; validated at import). `resolve(cookie, decl)` falls back per
field to defaults and never rewrites the cookie; reading a greyed or
undeclared Setting raises `SettingNotApplicable`. `recent_periods` /
`period_at` are the only data-dependent clamp (stored values stay as chosen).
`RULES`: `previous_period > current_period`; on read a failing pair renders
previous = current + 1, on save it is refused (only when both are
submitted). Storage: one JSON cookie `settings` (HttpOnly, SameSite=Lax,
path /, one year), written only by `POST /settings` (urlencoded form, parsed
with `parse_qsl`, 303 to a same-site `next`); a refused save sets a one-shot
`settings_error` cookie that opens the drawer once. Every page with the
shared nav renders through `render_with_settings` with a `NavContext`
(prefix, pages, current page/sub-page; pages are typed by the `NavPage`
protocol, which `Page` and `StatementPage` satisfy; the current sub-page by
`NavSubPage`, which `SubPage` satisfies); `shared/_page_nav.html`
names neither half of the app and hosts the gear + `<dialog>` drawer (Global
section; This page section for declared Sub-page Settings). No in-page
display controls exist; URLs carry no Settings.

**wizard.duckdb** `adjustment_preferences`: PK `adjustment_id`, unique
`(ticker, exchange, adjustment_type, base_concept)`; `base_concept` holds a
row id (name predates row ids). Types: `opex_to_capex` (value = years),
`owner_earnings` (maintenance %), `assets_in_use` (% in use for an asset
row, 1.0 = netted for a liability row). Each type is written by its
sub-page POST handler.

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
  `row_id`). Rows keyed by `row_id` (`row_id_col="row_id"`); a frame without
  it raises `TableSerializationError` (no ad-hoc id derivation).
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
- **Wiring** (`components/table_wiring.js`): table hydration (wizard
  sub-pages and the statement pages) — JSON →
  `TableModel.fromSerialized` → `render_table` → one `GenericInput` per slot;
  `input.subscribe` → `model.setCell`; `model.subscribe` → `input.set`.
  Must not read `input.value` / `input.checked`. Save posts
  `model.serialize()` (sub-pages with a save form: opex-to-capex,
  owner-earnings, assets-in-use). Convention: frontend module files that run
  wizard-page side effects wrap all their top-level execution in a single
  `main()` (or similarly named) function invoked once at the bottom, rather
  than having multiple bare top-level statements.
- **Statements**: one `Table` payload per page, embedded with the
  `line_item_table` macro and hydrated by `table_wiring.js`; no
  statement-specific JS. Fund Flow is a wizard sub-page built server-side.
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
- `find_row_id(key)` / `set_cell(column_id, row_id, value)`: write
  helpers used to inject saved wizard prefs into a `Table` before
  `serialize()`. `find_row_id` maps a stored pref key to a row id (exact match
  on `row_id_col` only); `set_cell` mutates
  the underlying DataFrame (adding the column if missing). `Table` is not
  read-only.

Embed: `{% table(id, data) %}` → JSON script + empty `<table>`;
`base_subpage.html` and `statements/statement_view.html` load
`components/table_wiring.js` to hydrate them. Tests: `tests/test_table.py`.

## 6. Status (short)

Working: vendor DuckDB + IndianAPI/AlphaVantage; edgartools fetch/cache;
`/statements/{t}/{statement}`; shared nav + Settings drawer; wizard shell +
opex table; Table used by statements + opex;
`TableModel` + `linked_groups` + view slots + `GenericInput` subscriptions in
`table_wiring.js` wired for opex-to-capex (receive, render, live edits,
linked-group math); prefs store (opex-to-capex save/prefill).

Partial: adjustments (opex-to-capex, owner-earnings and assets-in-use
save/prefill and restate); Finnhub; `load_to_database.py`.

NYI: wizard sub-pages other than One-line Answers, Balance Sheet Size, Fund
Flow, Capitalizing Opex, Owner Earnings and Assets in Use; screener;
analytics; finfetch.

Tests cover clients, DBs, edgartools, Table, wizard DB, Settings
(`test_settings.py`) and the page builders.
`test_settings_routes.py` is the only HTTP suite: TestClient over fixture
statements for the statements redirect and 404, `POST /settings` (redirect
guard, cookie attributes, refused saves), cookie round-trips and the drawer
per page. Cache miss hits live SEC. `pytest -m data` (deselected by default)
runs the data tests on real filings, once per ticker (the `data_ticker`
harness in `tests/conftest.py`) in the gitignored `tests/data_test_tickers.txt`
or, with `DATA_TICKERS=long`, `tests/data_test_tickers_long.txt`; tickers are
added to the company LRU pins and loaded through the app cache. `make test`
sets `REQUIRE_DATA_TESTS=1` (a missing prerequisite fails instead of skipping)
and first runs `scripts/link_worktree_files.py`, which symlinks the main
checkout's gitignored local files into a worktree.

## 7. Debt agents should not paper over

- No schema migrations by design (`CREATE TABLE IF NOT EXISTS` only); reset the
  DB after schema changes.
- Schema currency default `INR`; US data is USD — no FX layer.
- Alpha Vantage free tier 25/day.
- Dead exploration: `finfetch_client.py`, root `test_api_clients.py`,
  indianapi `deprecated.py` / `probe_api.py` — not patterns to copy.
