# Adjustments architecture

Status: design approved; phase 1 (cache + `Statement`, §10) implemented, phases 2–5 not.
Open tensions in §9 are unresolved.

## 1. Context

PR#4 saves opex-to-capex *preferences* but applies nothing. The statements page and
the wizard read raw edgartools bundles independently, with different `num_periods`
(10 vs 2) and therefore different row sets. We need one read-time pipeline that
applies saved adjustments, so that the statement view, the wizard snippets, and
later ROCE/red flags all see the same adjusted numbers. Adjusted numbers are never
persisted. Reported data and adjustment prefs stay fully decoupled.

### Verified facts this design relies on

| Fact | Evidence |
| --- | --- |
| summary ⊆ standard ⊆ detailed, row-wise | 27/27 cached (CIK × period × statement) bundles, keyed `(concept, label)` |
| Tier is derivable from the detailed frame plus one stored flag | edgartools 5.47 `Statement` filtering: summary drops every `dimension` row; detailed keeps all; standard drops rows where `is_breakdown` **and** dimensional rows whose member is not in the statement's presentation linkbase (`XBRL._get_valid_dimensional_members`, a filter detailed skips; e.g. AAPL iPhone/Mac/iPad on income). The cache stores that as `in_standard`; it matches `to_dataframe(view="standard")` row-for-row on 417 AAPL/MU/SNDK (filing, statement) pairs |
| `standard_concept` is not unique in detailed views | up to 12 dupes (income), 36 (cashflow). The opex table's `row_id_col="standard_concept"` can collide |
| Row sets depend on `num_periods` | AAPL annual_2 detailed income = 59 rows vs annual_10 = 113 |
| Calc linkbase reproduces reported totals **on raw signs** | AAPL & MSFT latest 10-K, all 3 statements: every monetary parent == Σ(weight × child) with `to_dataframe(presentation=False)`; with the default `presentation=True`, all 3 CF subtotals fail. The only miss was the diluted share count (an EPS-note-role arc; per-period statement-role edges, §6.1, don't include it) |
| `to_dataframe` exposes the calc tree | `parent_concept` = calculation parent, `parent_abstract_concept` = presentation parent, `weight` = calc weight for the statement role (only on `get_raw_data()` items; `to_dataframe`'s `weight` comes from the concept's first fact and can be another role's, so the cache takes the raw item's) |

## 2. Pipeline (where adjustments live)

```
edgartools ──(cache build, once)──► parquet: 3 Statement frames per (cik, period)
                                         │
                  load_statement_set(ticker, period)  → StatementSet (reported, immutable)
                                         │
 wizard.duckdb prefs ─► load_specs(ticker) ─► list[AdjustmentSpec]   (or draft specs from a POST body)
                                         │
                  apply_adjustments(base, specs, until=None) → StatementSet (adjusted, new object)
                                         │   engine: insert rows / override values → recompute dirty ancestors
                  compute_metrics(ss)  → EBIT, EBITDA, (later) owner earnings, ROCE
                                         │
                  ss.<stmt>.project(view, periods) → DataFrame → Table → serialize()  (FE contract unchanged)
```

- `src/adjustments/` is a pure domain package, with no FastAPI and no DB. The web
  layer does the I/O: context builders and the statements route load the base and
  the specs, call the engine, and project.
- The engine takes **specs as arguments**. It never reads the DB. That way a future
  "preview unsaved edits" endpoint can reuse it without writing anything.
- **Copy-on-apply.** The base comes from an LRU/parquet cache and must never be
  mutated. Optional in-process memo on `(ticker, period, cache meta, hash(specs))`.
  Never on disk.
- `src/adjustments/registry.py` is identity only (mirrors `wizard_registry.py`):
  `type_id → Adjustment class` + **pipeline order** (look-through → opex_to_capex →
  owner_earnings → assets_in_use).
- One module per type (`src/adjustments/types/opex_to_capex.py`), implementing:
  - `from_prefs(rows) -> Spec`
  - `apply(ss, spec) -> AdjustmentResult`, where the result is:
    - `new_rows`: each with `parent_concept` + `weight` + `tags`
    - `overrides`: `(statement, row_id) → per-period values`
    - provenance
  - Types never touch totals; the engine recomputes.
- Domain constants such as `OPERATING_EXPENSES` move into the type module. The
  wizard builder imports them from there.

## 3. Cache refactor

- **One detailed frame per statement.** Drop the 3×3 bundle. Per filing, call
  `to_dataframe(view="detailed", presentation=False)` **once**. The views become
  projections (§5).
- **Retain edgartools metadata.** `_build_view_dataframe` (rename to e.g.
  `_build_statement_dataframe`) must keep:
  - `abstract`, `dimension`, `is_breakdown`, `dimension_axis`, `dimension_member`,
    `dimension_member_label`, `dimension_label`
  - `balance`, `weight`, `preferred_sign`, `parent_concept`, `parent_abstract_concept`
  - alongside `concept`, `label`, `standard_concept`, `level`

  Per-row metadata is taken from the most recent filing the row appears in.
  **Exception: calc edges.** Filers restructure calc trees over the years, so
  each period also keeps the statement role's calc tree of the filing its values
  came from (`Statement.calc_edges`, cached as `{statement}_calc.parquet`); the
  frame's `parent_concept`/`weight` are newest-filing metadata only, never used
  for calc math.
- **Raw signs in cache.** Store raw values. Apply `preferred_sign` only at
  projection for display, so the numbers on screen are unchanged. The recompute
  needs raw signs (see the table in §1).
- **Cache key = `(cik, period)`**, with no `num_periods`.
  - New `MAX_CACHE_YEARS = 16` in `src/config.py`.
  - Annual caches ≤16 periods; quarterly caches ≤16×4 = 64 periods (or cap
    quarterly separately, see §9).
  - Requests slice `periods[:num_periods]` at projection. Clamp the route's
    `num_periods` bound to what's cached.
- **Bump a `schema_version` in `meta.json`** so old bundles are rebuilt. Existing
  staleness rules (`*_CACHE_MAX_AGE_MONTHS`) are unchanged.
- Fixes the known debts: the wizard no longer pays for 9 frames, and the wizard and
  statements pages see the same rows.

## 4. `Statement` / `StatementSet` (mirror edgartools `to_dataframe`)

- `src/models/statement.py`.
- `StatementSet { income, balance, cashflow: Statement, periods }`.
- `Statement` wraps a DataFrame whose columns are **exactly edgartools'
  `to_dataframe` metadata columns + period columns**, same names. It keeps `level`,
  not `depth`. We add only:
  - `row_id` (from `get_row_id`)
  - `tags` (e.g. `{"da"}`)
  - `origin` (`reported` | `adjustment:<type>`)
  - `is_total` (existing label heuristic)
  - `dimension_key` (derived edgartools metadata: every `axis=member` QName pair
    of a dimensional row, from `get_raw_data()`'s `dimension_metadata`;
    `to_dataframe` only exposes the primary pair)
  - `in_standard` (edgartools' standard-view membership, see §5)
- No per-statement subclasses. `statement_type` is an attribute.
- Methods:
  - `find(concept=… | standard_concept=…)`
  - `children(row_id, period)` (via that period's `calc_edges`; `weight` = the
    edge weight)
- `calc_edges`: long frame `period, concept, parent_concept, weight`, one calc
  tree per period (§3)
  - `insert(row, after=)`
  - `with_values(row_id, values)`
  - `project(view, periods) -> DataFrame`, which applies `preferred_sign` for
    display
- **Unified row id.** `get_row_id(row) -> str` in `src/models/statement.py` is the
  *only* place ids are formed: `concept`, plus every `axis=member` pair for
  dimensional rows (sorted by axis; axis namespace prefix stripped, member
  QName kept). A `#n` suffix disambiguates genuine repeats within one filing
  (e.g. cash at beginning/end of period).
  - Every consumer calls it: cache build, `Table` `row_id_col`, wizard builders,
    POST handlers, and `find_row_id`.
  - A test asserts uniqueness per statement.
  - Existing `adjustment_preferences.base_concept` rows are keyed by
    `standard_concept`. They need a one-off conversion or a re-save.

## 5. Views = projection by edgartools' own flags (no `min_tier` column)

```
summary  : dimension is False
standard : in_standard
detailed : all rows
```

`in_standard` is an added column computed at cache build: a detailed row is in
standard iff it matches a row of that filing's own
`to_dataframe(view="standard")` (aligned in order; standard only drops rows).
It cannot be derived from
`dimension`/`is_breakdown` alone. Like other metadata it comes from the newest
filing the row appears in; rows without it (e.g. inserted rows) default to
`not dimension or not is_breakdown`.

This is a pure function over retained columns. The name `level` stays reserved for
indent depth, and the filter parameter is `view`, matching edgartools. Filtering
hides rows, not value, so totals still include hidden children. Adjustment-inserted
rows are non-dimensional, so they appear in every view unless an adjustment marks
otherwise. Tier filtering can stay client-side (ship `dimension`/`in_standard` per
row) like today's toggle.

## 6. Totals: recompute along the calc linkbase (updated recommendation)

**Recommend recompute, using edgartools' calc tree, with guards.** The
calc tree is complete enough on real filings (§1), and it
replaces the hand-authored "spine" from v1 entirely.

1. **Residual per parent × period, on that period's own calc tree.** At load,
   compute `residual_p(P) = reported_p(P) − Σ_{c∈children_p(P)} w_p(c)·v_p(c)` over
   non-dimensional children, where `children_p` / `w_p` come from period `p`'s
   `calc_edges`: the statement-role calc tree of the filing `p`'s values came from
   (§3). Recompute uses `Σ w_p·child + residual_p`.
   - With zero specs this reproduces reported values exactly, even where a filer's
     calc tree is incomplete.
   - Residuals are expected to be 0 on real filings. Non-zero ones mean an
     incomplete filer tree or calc children the statement doesn't present
     (counted in `n_missing_children`).
   - Per-period trees are what avoid drift across years. A single (newest) tree
     applied to old periods would still reproduce zero-spec totals via the
     residual, but would route adjustment deltas along the wrong edges.
2. **Recompute only dirty ancestors, per period.** For each period `p`, walk
   `parent_p` upward from each overridden or inserted row and recompute
   `v_p(P) = Σ_{c∈children_p(P)} w_p(c)·v_p(c) + residual_p(P)`. Untouched subtrees
   keep reported values, so gaps and non-monetary rows (share counts) are never
   recomputed.
3. **Dimensional rows are excluded** from sums. They're parallel breakdowns, and a
   concept's calc edge is shared with its dimensional rows. If an
   adjustment overrides a concept that has dimensional rows, those rows are flagged
   stale rather than silently kept.
4. **Cross-statement links aren't in the calc linkbase.** The engine syncs the same
   concept across statements. Net income on IS feeds `NetIncomeLoss` on CF, then
   the CF recompute runs. Balance-sheet equity effects (retained earnings) are not
   derivable from the calc tree, so the adjustment emits them explicitly.

**Derived metrics** aren't calc-tree nodes, so they live in `src/adjustments/metrics.py`:
`EBIT = OperatingIncomeLoss`, `EBITDA = EBIT + Σ rows tagged "da"`. The new
depreciation row is tagged `da`. So adjusted EBIT falls by the depreciation, and
adjusted EBITDA rises by the full capitalized spend, with no special cases.

## 7. Opex-to-capex, all three statements (raw signs; parents resolved via `find(standard_concept=…)`)

For each capitalized row R with life N:

- **Asset math:**
  - `capitalized_t = spend_t`
  - `amort_t = Σ_{k=1..N} spend_{t−k}/N` (convention TBD, §9)
  - `net_asset_t = Σ unamortized`
  - Periods with fewer than N years of history are flagged partial.
Inserted rows' parents (and weights) are resolved per period from that period's
calc tree, since trees differ across years (e.g. `AssetsNoncurrent` exists only in
some years' trees).

- **IS:**
  - Override R → 0 (row kept, `origin` marked).
  - Insert `Depreciation (R)`: parent = R's calc parent (opex subtotal),
    weight = R's weight, tag `da`.
  - Recompute flows up to OperatingIncome → Pretax → NetIncome.
- **BS:**
  - Insert `Capitalized R (net)` under the non-current/total-assets parent.
  - Insert or override the equity offset of `cumulative (spend − amort)`, pre- or
    post-tax (§9), so that Assets == Liabilities + Equity.
- **CF:**
  - NetIncome syncs from IS.
  - Insert `Depreciation (R)` add-back under the CFO parent (tag `da`).
  - Insert `Capitalized R` outflow under the CFI parent.
  - CFO rises by the spend and CFI falls by the spend. The net change in cash is
    unchanged, and that's an invariant to test.

## 8. Consumers

- **Statement view:**
  - Route: `load → load_specs → apply → project`.
  - Ships both `reported` and `adjusted` sets: payload is 3 statements × 2 bases,
    down from 3×3.
  - A basis toggle in `statement_view.js`.
  - Generic optional `origin` row field in `Table.serialize()` / `TableModel`, for
    styling. This is allowed in shared files because it's generic.
- **Wizard snippets use stage semantics.** The snippet for adjustment X renders
  `apply(base, specs, until=X)`, which is the input to X.
  - The opex-to-capex page shows pre-capitalization opex, so R&D is still pickable.
  - Owner-earnings shows D&A after opex-to-capex.
  - Snippet selection (`ss.income.find(...)` / filter by `OPERATING_EXPENSES`)
    stays in `wizard_pages/<name>.py`. The optional "after" preview is `until=None`.
- **Preview (later):** generic `POST …/preview` that runs the engine on
  `model.serialize()` without saving. No adjustment math in JS.

## 9. Open tensions (responses in subpoints)

1. **Tax effect** on the IS/equity delta: none (pre-tax), or effective rate?
  - Use the reported tax amount, don't compute tax rate.
2. **Amortization convention:** start the year after spend or same year, and
   half-year or not?
  - Start in the same year. Any deferred amortization will go in WIP (future scope)
3. **Quarterly history:** cache 64 10-Qs (slow cold fetch)? Or annual-only
   adjustments, or quarterly derived from annual schedules?
  - Cache all the 10-Qs.
4. **Spend source per period:** R's reported value in that period. What happens if R
   is missing in old filings (concept renamed)? Is `standard_concept` fallback
   acceptable?
  - Leave open for now. This will have to be a separate feature with its own handling.
5. **Where the BS asset row hangs:** `AssetsNoncurrent` if the filer reports it,
   else `Assets`. Is it acceptable to add a missing subtotal?
  - Don't add a missing subtotal. Resolve the parent per period: a filer may have
    `AssetsNoncurrent` in some years' calc trees and not others.
6. **Prefs schema:** `value DOUBLE` is too narrow for later types. `params JSON`?
   There are no migrations today.
  - Keep it as is for now.
7. **Existing prefs keyed by `standard_concept`:** convert or drop?
  - Convert it, but everything should be routed through get_row_id

## 10. Implementation phases & critical files

1. **Cache + Statement.**
   - `src/config.py` (`MAX_CACHE_YEARS`)
   - `src/api/edgartools/source.py`, `cache.py`
   - new `src/models/statement.py` (`Statement`, `StatementSet`, `get_row_id`,
     projection)
   - `src/models/edgartools/html_renderer.py`, `src/web/routes/statements.py`,
     `static/js/statement_view.js` (view via projection; display unchanged)
2. **Row-id unification.**
   - `src/models/table.py` (`find_row_id` via `get_row_id`)
   - `wizard_pages/adjustments_context.py`, `adjustments_post.py`
   - prefs conversion
3. **Engine.** `src/adjustments/{engine,registry,metrics}.py`: residuals, dirty
   recompute, cross-statement sync. Test: `apply(base, [])` == reported.
4. **Opex-to-capex type.** `src/adjustments/types/opex_to_capex.py`, IS + BS + CF.
5. **Consumers.** Statements basis toggle, `origin` row field, wizard `until=` stages.

## 11. Verification

- Projection parity: `project(view)` with display signs equals today's
  summary/standard/detailed parquet frames, for all cached tickers.
- Calc reconciliation report: residual distribution across all cached tickers ×
  periods, each period on its own calc tree. Parents should be 0; list the
  non-zero ones (with `n_missing_children`).
- `apply(base, [])` == reported, bit-for-bit.
- `get_row_id` is unique per statement for every cached bundle.
- Opex-to-capex on AAPL:
  - ΔEBIT = spend − depreciation
  - ΔEBITDA = spend
  - Assets − (Liabilities + Equity) == 0
  - ΔCFO = +spend, ΔCFI = −spend, Δ net cash = 0
  - early periods flagged partial
- Wizard opex page still lists R&D (stage input). The statements adjusted basis
  shows the new rows.
- `pytest`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`

