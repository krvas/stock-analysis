# Spec: estimated depreciation per PP&E class (Owner Earnings)

Status: **future scope, not scheduled.** Nothing here is built.
Owner: Krish (single user, local app).
Related: `specs/vision.md` ("Owner's Earnings Calculations"),
`specs/adjustments_architecture.md` (§2 pipeline, §8 consumers),
`specs/STATE.md` (§3 hard rules, §4 row ids, §5 Table contract).

## 0. Baseline this spec builds on

| Piece | State |
| --- | --- |
| Owner Earnings page (`wizard_pages/owner_earnings.py`, `adjustments/types/owner_earnings.py`) | Built: one maintenance % for all of D&A, one for ΔNWC. |
| D&A components from the filing notes | **In progress (separate work), treated as done here.** The cache adds note facts (`us-gaap_Depreciation`, `us-gaap_AmortizationOfIntangibleAssets`, `us-gaap_FinanceLeaseRightOfUseAssetAmortization`, …) as breakdown rows under the cash-flow D&A line (`is_breakdown=True`, `in_standard=False`, detailed view only). Each has its own `row_id`; the saved maintenance % is keyed by that row id. |
| `origin` row field | Exists. `Statement` defaults it to `"reported"`; inserted rows must set one (e.g. `"adjustment:opex_to_capex"`). `Table.serialize()` passes it to the frontend; `table_view.js` styles `adjustment:*` rows. |

Verified data facts (AAPL, MU, SNDK):

- No filer tags depreciation **expense** by PP&E class.
- `us-gaap_PropertyPlantAndEquipmentByTypeAxis` appears only on gross PP&E
  **balances** (e.g. buildings, machinery and equipment, land).
- Each 10-K's notes cover 3 fiscal years of flow facts.

## 1. Problem statement

Buffett's owner earnings deducts *maintenance* capex: the spend needed to keep
the existing business running. Maintenance intensity varies by asset type.
Buildings may need little reinvestment beyond their depreciation, while
equipment and computing hardware are replaced on short cycles. After the
baseline, the user can set a separate % for depreciation and for amortization
of intangibles. But depreciation is still one number, because filers don't
report it by asset class. For capital-heavy filers like MU, nearly all of D&A
is depreciation, so one blended % hides the asset mix the user is trying to
judge. Without this feature, the user has to estimate the per-class split
outside the app, which breaks the rule that the app stores **rules** that
re-apply on refreshed filings.

## 2. Goals

1. The user can set a maintenance % for each PP&E class (buildings, machinery
   and equipment, leasehold improvements, …) instead of one % for all of
   `Depreciation`.
2. Per period, the estimated per-class depreciation sums **exactly** to the
   reported `Depreciation`. Estimation reallocates the reported total and never
   changes it.
3. Every estimated number is visibly marked as an estimate, in the data
   (`origin`) and in the UI, together with the method and inputs used.
4. Saved per-class % values survive a cache rebuild or a new 10-K without
   re-entry, as long as the filer keeps the same PP&E class members.
5. Owner earnings with per-class % equals the baseline result when every class
   % equals the `Depreciation` %. This is a regression invariant.

## 3. Non-goals

- **Estimating amortization by intangible class.** It's a separate concept
  with a separate axis, so the same pattern can be reused later.
- **Quarterly per-class estimates.** 10-Qs rarely carry the PP&E-by-class
  note (unverified). v1 covers annual periods only.
- **Persisting estimates.** The parquet cache stays reported data only, and
  estimates are computed at read time like every other adjustment.
- **Cross-company class normalization.** Mapping `aapl_…Member` to a canonical
  "machinery" class is out of scope, because the EDGAR slice isn't
  cross-company (STATE §1).
- **Automatically detecting maintenance vs growth capex from MD&A text.** That's
  a separate vision item.
- **Showing estimated rows on `/statements`.** v1 shows them on the Owner
  Earnings page only (see open question Q6).

## 4. User stories

- As the analyst, I want to see the reported depreciation split into estimated
  per-class amounts, so that I can judge maintenance needs per asset type.
- As the analyst, I want a different maintenance % per PP&E class, so that
  owner earnings reflects the asset mix rather than one blended guess.
- As the analyst, I want estimated rows to look visibly different from reported
  rows and to show how they were derived, so that I never mistake an
  allocation for a filed number.
- As the analyst, I want my per-class % to still apply after a new 10-K is
  cached, so that the page updates without re-entry.
- Edge: as the analyst, when a period has no class breakdown, I want the class
  rows blank and the `Depreciation` % to apply, so that owner earnings still
  computes.
- Edge: as the analyst, when the filer renames or drops a class member, I want
  to be told that a saved % no longer matches a row, so that I can set it
  again.

## 5. Data sources and coverage risks

| Input | Source | Risk |
| --- | --- | --- |
| Reported `Depreciation` per period | Baseline D&A component row (`us-gaap_Depreciation`) | Some filers report only `DepreciationDepletionAndAmortization` or `DepreciationAmortizationAndAccretionNet`. With no `Depreciation` row there's nothing to allocate, so the feature is off for that period. |
| Gross balance per class | Note facts `us-gaap_PropertyPlantAndEquipmentGross` with `PropertyPlantAndEquipmentByTypeAxis` members. **Not in the cache today**: the cache holds only the 3 face statements. It needs the same note-fact ingestion as the baseline, as reported breakdown rows under the balance-sheet PP&E line. | The gross concept may vary by filer (e.g. `…BeforeAccumulatedDepreciationAndAmortization`, or ROU-inclusive variants). Class members are partly standard (`us-gaap_LandMember`, `us-gaap_BuildingAndBuildingImprovementsMember`, `us-gaap_MachineryAndEquipmentMember`, `us-gaap_ConstructionInProgressMember`, `us-gaap_LeaseholdImprovementsMember`) and partly filer-specific. |
| Balance dates per 10-K | PP&E note | Unverified: a balance note usually has 2 year-ends, while flow notes have 3. An average balance for the oldest flow year may need the previous 10-K. |
| Useful lives per class (life-weighted method only) | `us-gaap_PropertyPlantAndEquipmentUsefulLife` (+ `…Minimum`/`…Maximum`) by class member | Often reported as ranges, sometimes only in text (not XBRL), and sometimes on a different member set than the balances. Unverified for AAPL/MU/SNDK. |
| Gross PP&E total | `PropertyPlantAndEquipmentGross` non-dimensional | Classes may not sum to the total. The difference becomes an "Other / unallocated" class. |

## 6. Estimation approaches

Notation, per period *t*: `D` = reported `Depreciation`; `G_c` = gross balance
of class *c* (average of opening and closing if both exist, else closing; see
Q3); `L_c` = useful life of *c*; `E` = the set of **depreciable** classes.

**Excluded from `E` by default:** land (not depreciated), construction in
progress (not depreciated until placed in service), and finance-lease ROU
assets when ROU amortization is its own D&A component (otherwise it's counted
twice; see Q4). The exclusion list is a domain constant (concept/member QNames
go in `src/api/edgartools/standard_terms.py`).

### A. Gross-balance share (v1 default)

`dep_c = D × G_c / Σ_{k∈E} G_k`

- + Needs only the class balances, which are verified to exist.
- + Always sums to `D`.
- − Assumes equal useful lives. It over-allocates to long-lived classes.
  Example: buildings and equipment at 50/50 gross, with lives of 40 and 5
  years. Gross share gives 50/50; life-weighted gives about 11/89. This bias
  is large exactly where the feature matters most.
- − Gross includes fully depreciated assets that are still in use. Old
  equipment inflates its share.

### B. Useful-life-weighted share

`dep_c = D × (G_c / L_c) / Σ_{k∈E} (G_k / L_k)`

- + Much closer to straight-line reality when the mix of asset lives is wide.
- − Needs `L_c`. If a range is disclosed, use the midpoint (Q5). If any
  depreciable class has no life, fall back to method A for that period and
  record the fallback in the provenance.
- − Still ignores the age of the assets.

### C. Accumulated-depreciation roll-forward (P2)

`dep_c ≈ ΔAccumDep_c + disposals_c`. This is exact if disclosed, but accumulated
depreciation is almost always reported as a single total, so it's listed for
completeness only.

### Shared rules

- If `E` is empty or `D` is missing for a period, no class rows are produced
  for that period.
- If Σ classes < gross total, the residual goes to an "Other / unallocated"
  class (a depreciable class with its own % input). If Σ classes > total,
  allocate over the classes and log it.
- Methods only reallocate `D`. They never change `D`, the D&A total, or other
  components.

## 7. Placement (repo rules)

| Concern | Lives in | Why |
| --- | --- | --- |
| Gross-by-class note facts in the cache | `src/api/edgartools/source.py` (same mechanism as the baseline D&A note facts) | Reported data. Generic note-fact ingestion, with no logic specific to Owner Earnings. |
| Concept/member QNames, exclusion list | `src/api/edgartools/standard_terms.py` | Already the home for domain term names. |
| Allocation math (A/B), pure | A function in `src/adjustments/types/owner_earnings.py`, or a sibling pure module in `src/adjustments/` if another type needs it | Domain package, no I/O (architecture §2). |
| Table rows, % inputs, POST keys | `src/web/routes/wizard_pages/owner_earnings.py` | Builders = data. Subpage-specific constants are correct here. |
| Markup and provenance text | `src/templates/wizard/<page>/owner-earnings.html` (`source_trace` block) | Subpage-specific template. |
| Estimate styling | `table_view.js` may add a **generic** rule keyed on an `origin` prefix (e.g. `estimate:*`), alongside the existing `adjustment:*` rule | Passes the CLAUDE.md test: the line works unchanged for any table. No slug, field or row-id literals. |
| `wizard_registry.py`, `routes/wizard.py`, `table.py`, `table_model.js`, `table_wiring.js` | **No changes expected** | The page already exists. Rows and inputs flow through the existing Table contract. |

## 8. Provenance (estimate vs reported)

- **Data.** Estimated rows are inserted at read time with
  `origin = "estimate:ppe_depreciation:<method>"` (`gross_share` |
  `life_weighted` | `gross_share_fallback`) and tags `("da", "estimate")`.
  Gross balances and `Depreciation` keep `origin = "reported"`. The cache never
  holds estimate rows.
- **Per-period provenance record** returned by the allocation function: method
  used, classes included and excluded (with reason), the `G_c` / `L_c` values
  used, and the residual. The builder renders it in `source_trace`.
- **UI.** Labels end in "(est.)". Rows are styled through the generic
  `origin` rule. The class rows are indented under the reported `Depreciation`
  row, and a footnote states the method in one sentence.
- **Never** label an estimated row with the filer's own label alone.

## 9. Saved % key stability

- **Key = estimated row's `row_id` via `get_row_id`** (the only place ids are
  formed; STATE §3). Proposal: concept `us-gaap_Depreciation` + the class's
  `PropertyPlantAndEquipmentByTypeAxis=<member QName>`. Because it's built
  from the filer's member QName, the key stays the same across refreshes as
  long as the member does. This is also exactly the id a reported per-class
  depreciation fact would get, so the % carries over if a filer starts tagging
  it.
- **Collision rule.** If a reported row with that id exists, the reported row
  is used and no estimate is inserted. Row ids stay unique (`Statement.insert`
  raises on duplicates).
- **Residual class key.** A fixed synthetic id (e.g.
  `us-gaap_Depreciation|PropertyPlantAndEquipmentByTypeAxis=adj_OtherUnallocated`).
  Needs `get_row_id` to accept it (Q7).
- **Fallback chain for an unset class %:** class % → `Depreciation`
  component % → D&A %. The totals then match the baseline (Goal 5).
- **Orphans.** A saved key with no matching row in any shown period is listed
  on the page as "saved % not applied (class no longer reported)". It isn't
  deleted automatically (no backfills or migrations; STATE §3).
- **Method choice.** If the user can pick A or B, that choice is a saved pref
  too. `adjustment_preferences.value` is `DOUBLE` only (architecture §9.6), so
  this is an open question (Q8).

## 10. Requirements

### P0

1. Ingest gross PP&E balances by `PropertyPlantAndEquipmentByTypeAxis` member
   into the cache as reported breakdown rows (detailed view only).
2. Method A allocation for annual periods, with land, CIP and (conditionally)
   ROU excluded, plus an "Other / unallocated" residual class.
3. Estimated class rows on the Owner Earnings page under `Depreciation`, each
   with a maintenance % input. Provenance appears in `origin` and in
   `source_trace`.
4. Saved % keyed by row id, the fallback chain, and the orphan notice.
5. Owner earnings = Σ (component or class amount × its %) for maintenance D&A,
   with no double counting between `Depreciation` and its classes.

### P1

- Method B (life-weighted), with a per-period fallback to A.
- User override of `L_c` per class (another keyed pref).
- Method picker on the page.

### P2

- Method C when accumulated depreciation is disclosed by class.
- The same pattern for amortization by intangible class.
- Estimated rows on the adjusted `/statements` basis.

## 11. Acceptance criteria

- [ ] For every annual period with `D` and ≥1 depreciable class: Σ estimated
      class depreciation == `D`, to the cent (unit test plus a `pytest -m data`
      check on AAPL/MU/SNDK).
- [ ] Land and CIP rows never receive depreciation. Given a filer whose only
      classes are land and CIP, no class rows appear and the `Depreciation` %
      applies.
- [ ] Given every class % == the `Depreciation` %, owner earnings equals the
      baseline value for every period.
- [ ] Given a class % is saved, when the cache is deleted and rebuilt, the same
      % is pre-filled on the same class row.
- [ ] Given a saved key whose member is no longer reported, the page shows the
      orphan notice, and the saved % has no effect on the result.
- [ ] Given a period with no class balances, its class cells are blank, there's
      no error, and owner earnings uses the fallback %.
- [ ] Every estimated row has an `origin` starting with `estimate:`, is
      visibly distinct, and is labelled "(est.)". No reported row carries that
      origin.
- [ ] The parquet cache contains no estimate rows.
- [ ] No subpage slugs, field names or class-member literals appear in the
      shared files listed in `CLAUDE.md`. `make test` passes.
- [ ] (P1) With method B, a building/equipment mix with lives 40/5 at 50/50
      gross allocates about 11/89.

## 12. Success measures (personal tool)

- Coverage: the share of cached annual periods (AAPL/MU/SNDK, then any pinned
  ticker) that get class rows. Target: the latest 3 fiscal years for all
  three tickers.
- Reconciliation: the allocation residual vs `D` is 0 in 100% of periods.
- Usefulness check: owner earnings with per-class % differs from the blended
  result enough to change a judgement on at least one ticker. If it never
  does, keep the blended input and drop P1.

## 13. Open questions (for the owner)

| # | Question | Blocking? |
| --- | --- | --- |
| Q1 | Does the PP&E balance note use the same gross concept and member set in every year for AAPL/MU/SNDK? Which filer-specific members appear? | Yes (data check before P0.1) |
| Q2 | Is `us-gaap_Depreciation` reported for all three tickers in every cached year, or only `DepreciationDepletionAndAmortization` in some years? | Yes |
| Q3 | Weight by closing or average gross balance? Does each 10-K's balance note give 2 dates (unverified) so the oldest flow year needs the previous 10-K? | No (default: average if both dates exist, else closing) |
| Q4 | For each filer, does `Depreciation` include finance-lease ROU amortization? This decides whether ROU classes are excluded from `E`. | Yes, per filer |
| Q5 | Useful-life ranges: use the midpoint, the minimum or the maximum? Use XBRL facts only, or also parse text? | No (P1) |
| Q6 | Should estimated rows also appear on `/statements` (adjusted basis), or stay on the wizard page only? | No |
| Q7 | Is a synthetic member (`adj_OtherUnallocated`) acceptable in `get_row_id`, or should the residual use a separate synthetic concept? | No |
| Q8 | How should the method choice and life overrides be stored, given `value DOUBLE` (architecture §9.6)? Encode as a numeric code, or widen the schema? | No (P1) |
| Q9 | Should % inputs on classes be allowed together with a % on the parent `Depreciation` row (parent = default), or should the parent input be disabled once classes exist? | Yes (UX) |

## 14. Timeline and phasing

There are no deadlines. Dependencies, in order:

1. Baseline D&A component rows (in progress).
2. Q1, Q2, Q4 data checks.
3. P0 (ingestion → method A → page → keys).
4. P1 (method B, overrides).

Each step is a separate atomic commit, following the repo workflow in
`CLAUDE.md`.
