# Spec: Growth Estimation

- **Status:** ready for agent, not built
- **Depends on:** `owner-earnings-exceptional-items.md` (Owner Earnings excludes exceptional items), `assets-in-use.md` (Net Assets in Use, the ROCE denominator), `roce.md` (`valuation_inputs` table, ROCE / After-tax Owner Earnings / Distributions / Retained Earnings metric functions)
- **Consumed by:** `neff-ratio.md` (reads each Scenario's Owner Earnings CAGR)
- **Related docs:** `CONTEXT.md` (glossary), `specs/adjustments_architecture.md` §6 (planned metrics module), `specs/vision.md` (Page 5 – Valuation), the One-line Answers page (AI task prior art), the Owner Earnings page (input table + save prior art)

## Problem Statement

Once I know what a business earns (Owner Earnings) and how good it is (ROCE), I still have to answer the question every valuation rests on: where will this company be in five years? What will its revenue be, and what share of that revenue will turn into Owner Earnings? Today the Growth Estimation sub-page is an empty stub. To form a view I have to pull revenue history out of the statements by hand, compute margins and CAGRs in a spreadsheet, work out how fast the business could grow from the capital it keeps, and read years of 10-Ks for guidance, segment trends, capacity additions, market size and pricing. Then I have nowhere to write down my bear, base and bull views, so the Neff Ratio page has no growth figure to use.

## Solution

The Growth Estimation sub-page on the Valuation page puts three sources of evidence on one dashboard and asks me for my five-year view, per Scenario:

1. **History**: revenue, Owner Earnings and Owner Earnings margin for every cached annual period, with 5- and 10-year CAGRs of revenue and Owner Earnings.
2. **Reinvestment-implied Growth**: ROCE × Reinvestment Rate, both averaged over the latest five years. Each year has an include checkbox (all ticked by default); unticking a year shrinks the window and the page says so ("averaged over 4 of 5 years").
3. **AI digest** of the 10-Ks: management guidance, segment growth, capacity expansions, market size and pricing, each item with its sources.

Below the evidence, I pick a Scenario (bear / base / bull) with a toggle and enter two numbers for it: year-5 revenue and year-5 Owner Earnings margin. The page computes year-5 Owner Earnings and its CAGR from the base year (the latest annual period). Figures are whole-company, not per share. The base Scenario is required; bear and bull are optional. My inputs and my excluded years are saved and come back when I return. The page is annual only.

## User Stories

1. As the investor, I want the Growth Estimation sub-page to open from the Valuation page, so that I can estimate growth right before valuing the company.
2. As the investor, I want the page to state the question it answers ("Where is this company in 5 years? What is its revenue? What is its Owner Earnings margin then?"), so that I know what I am being asked to decide.
3. As the investor, I want to see revenue for every cached annual period, so that I can see the long-run trend, not just the last few years.
4. As the investor, I want to see Owner Earnings for every cached annual period, so that I can compare earnings growth with revenue growth.
5. As the investor, I want to see the Owner Earnings margin (Owner Earnings ÷ revenue) for every cached annual period, so that I can judge whether margins are stable, expanding or shrinking.
6. As the investor, I want the 5-year CAGR of revenue and of Owner Earnings, so that I have a recent growth reference.
7. As the investor, I want the 10-year CAGR of revenue and of Owner Earnings, so that I have a longer, cycle-spanning growth reference.
8. As the investor, I want a CAGR shown as unavailable (with the reason) when there are not enough years of history, so that I do not mistake a short window for a long one.
9. As the investor, I want a CAGR shown as unavailable when its start or end value is zero or negative, so that I am not shown a meaningless growth rate.
10. As the investor, I want a year whose Owner Earnings cannot be computed (e.g. pre-tax income missing) shown as unavailable rather than zero, so that gaps are visible.
11. As the investor, I want the Owner Earnings on this page to be the same number the Owner Earnings page produces (post all adjustments, excluding exceptional items), so that every page agrees.
12. As the investor, I want to see ROCE for each of the latest five years, so that I can see how much each unit of capital earned.
13. As the investor, I want to see the Reinvestment Rate (Retained Earnings ÷ pre-tax Owner Earnings) for each of the latest five years, so that I can see how much of earnings the business kept.
14. As the investor, I want the Reinvestment Rate to use pre-tax Owner Earnings in the denominator, so that ROCE × Reinvestment Rate stays on one tax basis.
15. As the investor, I want the 5-year average ROCE, the 5-year average Reinvestment Rate and their product (Reinvestment-implied Growth), so that I have a growth figure grounded in capital the business retains.
16. As the investor, I want an include checkbox on each of the five years, ticked by default, so that I can drop a distorted year (an acquisition year, a one-off) from the averages.
17. As the investor, I want unticking a year to shrink the averaging window rather than count the year as zero, so that excluding a year does not drag the average down.
18. As the investor, I want the page to say "averaged over k of 5 years", so that I always know how many years stand behind the figure.
19. As the investor, I want a company with fewer than five years of usable data to be averaged over the years it has (and labelled "k of 5"), so that young companies still get a figure.
20. As the investor, I want a year whose ROCE or Reinvestment Rate cannot be computed to be shown as unavailable and left out of the averages, so that missing data never silently becomes zero.
21. As the investor, I want the page to say when no years are included, instead of showing a number, so that I am not shown an average of nothing.
22. As the investor, I want my excluded years saved, so that they are still excluded when I come back.
23. As the investor, I want to re-tick an excluded year to include it again, so that exclusions are reversible.
24. As the investor, I want the ROCE on this page to be the same ROCE the ROCE page shows, so that the two pages never disagree.
25. As the investor, I want an AI digest of the 10-Ks covering management guidance, segment growth, capacity expansions, market size and pricing, so that I do not have to read every filing to find growth evidence.
26. As the investor, I want each digest item to list its sources (fiscal year and 10-K Item), so that I can check the claim in the filing.
27. As the investor, I want a digest category with nothing in the filings to say so, so that I know the AI looked and found nothing rather than failing.
28. As the investor, I want the digest to show a "being generated" notice while the AI is still working, while the rest of the page (history, Reinvestment-implied Growth, Scenarios) still works, so that I am not blocked by the AI.
29. As the investor, I want the digest cached against the latest 10-Ks, so that it is not regenerated on every visit and refreshes when a new 10-K is filed.
30. As the investor, I want to see the base year (the latest annual period) with its revenue, Owner Earnings and Owner Earnings margin, so that I know what my five-year view grows from.
31. As the investor, I want the horizon fixed at five years, so that every Scenario and the Neff Ratio page use the same horizon.
32. As the investor, I want to enter a year-5 revenue for a Scenario, so that I can state where I think the top line will be.
33. As the investor, I want to enter a year-5 Owner Earnings margin for a Scenario, so that I can state how profitable I think the business will be.
34. As the investor, I want the page to compute year-5 Owner Earnings (year-5 revenue × year-5 margin), so that I do not do arithmetic by hand.
35. As the investor, I want the page to compute the Owner Earnings CAGR from the base year to year 5, so that I get the growth rate the Neff Ratio uses.
36. As the investor, I want figures to be whole-company, not per share, so that buybacks are treated as Distributions rather than double counted as per-share growth.
37. As the investor, I want a toggle to switch between bear, base and bull, editing one Scenario at a time, so that the form stays simple.
38. As the investor, I want the base Scenario to be required, so that the Neff Ratio page always has at least one growth figure.
39. As the investor, I want bear and bull to be optional, so that I can stop at one view when I have no strong range.
40. As the investor, I want a clear notice while the base Scenario is empty, so that I know the page is not finished.
41. As the investor, I want a summary of every filled-in Scenario's year-5 revenue, margin, year-5 Owner Earnings and CAGR, so that I can compare my views side by side.
42. As the investor, I want my Scenario inputs saved, so that I can come back and refine them.
43. As the investor, I want to clear an optional Scenario by emptying both fields and saving, so that I can withdraw a view.
44. As the investor, I want a save with only one of the two fields filled to be rejected with a message, so that half-filled Scenarios never reach the Neff Ratio page.
45. As the investor, I want invalid input (non-numbers, negative revenue, a margin outside −100% to 100%) rejected with a message, so that bad numbers are never stored.
46. As the investor, I want the CAGR shown as unavailable, with the reason, when base-year Owner Earnings or year-5 Owner Earnings is zero or negative, so that I am not shown a meaningless rate.
47. As the investor, I want the page to tell me when base-year Owner Earnings cannot be computed (naming the year), so that I know why no CAGR appears.
48. As the investor, I want to enter year-5 revenue in the same unit the page displays (millions), so that I can type numbers that look like the history above.
49. As the investor, I want the computed figures to refresh after I save, so that what I see always matches what is stored.
50. As the investor, I want `period=quarterly` to show an "annual only" notice, so that I am not shown annual numbers mislabelled as quarterly.
51. As the investor, I want inputs keyed to the ticker, so that one company's Scenarios never leak into another's.

## Implementation Decisions

### Registry and page wiring
- The existing Growth Estimation sub-page entry on the Valuation page (order 1) gets a context builder and a POST handler from a new wizard-page module for this sub-page. The registry stays identity only.
- The sub-page template lives under the Valuation page's template folder and follows the existing sub-page layout.
- When `period` is not annual, the context builder returns only an annual-only flag and the template shows the shared annual-only notice (cross-cutting; see Assumptions).

### Owner Earnings and revenue per year
- Owner Earnings per annual period comes from the fully adjusted statement set (all adjustment stages applied), from the Owner Earnings memo row that the owner_earnings adjustment inserts. It therefore reflects `owner-earnings-exceptional-items.md` and the saved maintenance %. The owner_earnings adjustment only runs when the ticker has a saved owner_earnings preference; how the metrics get Owner Earnings when none is saved (unset maintenance % = 0) is defined by `roce.md`, and this page uses that same path.
- Revenue per annual period is the income-statement row whose standard concept is `Revenue` (first non-dimensional match), named as a domain constant in the edgartools standard-terms module.
- Owner Earnings margin = Owner Earnings ÷ revenue. Unavailable when revenue is missing or zero.

### Pure metrics (in the adjustments package's metrics module)
This spec adds these functions. ROCE, After-tax Owner Earnings, Distributions and Retained Earnings are defined by `roce.md` and reused here, not redefined.

- **CAGR**: `cagr(start, end, years) = (end ÷ start)^(1 ÷ years) − 1`. Returns "unavailable" (None) when either value is missing, either is ≤ 0, or `years` ≤ 0.
- **Historical CAGR over n years**: for a per-period series ordered newest first, uses the latest period and the period n years earlier (needs n + 1 periods). Unavailable if either endpoint is missing. Used for n = 5 and n = 10, for revenue and Owner Earnings.
- **Reinvestment Rate** per period = Retained Earnings ÷ pre-tax Owner Earnings. Unavailable when Retained Earnings is unavailable or Owner Earnings is missing or ≤ 0.
- **Reinvestment-implied Growth** over a window: inputs are per-period ROCE, per-period Reinvestment Rate, and the set of excluded periods. Included periods = window periods not excluded and with both ROCE and Reinvestment Rate available.
  - average ROCE = mean of ROCE over included periods
  - average Reinvestment Rate = mean of Reinvestment Rate over included periods
  - Reinvestment-implied Growth = average ROCE × average Reinvestment Rate
  - Returns the two averages, the product, the included count k and the window size (5). With k = 0 all three figures are unavailable.
- **Scenario Owner Earnings**: year-5 Owner Earnings = year-5 revenue × year-5 margin ÷ 100; Scenario CAGR = `cagr(base-year Owner Earnings, year-5 Owner Earnings, 5)`.
- The window is the latest five annual periods (the horizon constant, 5, is shared by the window and the Scenario CAGR).

### Stored inputs (`valuation_inputs`, defined by `roce.md`)
Rows use `subpage = growth-estimation`. This spec adds these input keys:

| input_key | value | meaning |
| --- | --- | --- |
| `scenario.<bear\|base\|bull>.revenue_y5` | full currency units (the page multiplies the millions input by 1,000,000) | year-5 revenue |
| `scenario.<bear\|base\|bull>.oe_margin_y5` | percent (e.g. 18.5 = 18.5%) | year-5 Owner Earnings margin |
| `exclude.<period end date>` | 1.0 | that year is excluded from the Reinvestment-implied Growth averages; absent = included |

- Writes go through the `valuation_inputs` operations on the wizard database manager defined by `roce.md` (read for a ticker and subpage, upsert, delete by key). If `roce.md` does not provide a delete-by-key operation, this spec adds it there.
- The input keys and a small loader that returns each filled-in Scenario (revenue, margin, year-5 Owner Earnings, CAGR) live in this sub-page's module. `neff-ratio.md` reuses that loader rather than re-reading keys.

### Context builder (data)
Returns, for annual:
- the base year (latest annual period) with its revenue, Owner Earnings and margin, or a notice naming the year if its Owner Earnings cannot be computed;
- a history Table: one row per metric (revenue, Owner Earnings, Owner Earnings margin), one static column per cached annual period, plus static 5-year and 10-year CAGR columns (margin row has no CAGR);
- a Reinvestment-implied Growth Table: one row per window year, static columns ROCE and Reinvestment Rate, and a boolean input column "Include" (ticked unless saved as excluded). Years with an unavailable metric show it as unavailable and their Include cell is a no-input cell. Alongside it: average ROCE, average Reinvestment Rate, Reinvestment-implied Growth and "averaged over k of 5 years";
- one Scenario Table per Scenario: rows Revenue, Owner Earnings margin, Owner Earnings; columns base year (static) and year 5. Year-5 revenue and margin are input cells; year-5 Owner Earnings is static, computed server-side from saved inputs. The Scenario's CAGR (or the reason it is unavailable) is returned with the Table;
- a summary of filled-in Scenarios and a flag for "base Scenario missing";
- the AI digest answer, or a digest-pending flag.

Row ids in the Scenario Tables are namespaced by Scenario (e.g. `base.revenue`); row ids in the Reinvestment Table are `year.<period end date>`. All Tables use the existing Table payload contract.

### Template and toggle
- The Scenario toggle is a query parameter (`scenario=bear|base|bull`, default `base`, unknown values fall back to `base`), read in the template the way One-line Answers reads `view`. Only the selected Scenario's Table and form are rendered.
- Two forms, both posting to the sub-page's POST URL with `model.serialize()`: one for the Reinvestment Table (include checkboxes), one for the selected Scenario Table. No subpage-specific JavaScript.
- After a successful save the page reloads so server-computed figures (averages, year-5 Owner Earnings, CAGRs) refresh. This needs a generic "reload after save" option on the wizard form macro and save wiring; it references no subpage and passes the shared-file test in `CLAUDE.md`.
- The digest section shows the shared AI pending partial when pending; history, Reinvestment-implied Growth and Scenarios render regardless.

### POST handler
- Accepts the serialized Table body (`rows: [{id, cells}]`). Dispatches by row-id prefix; rows from one form only are expected per request, but the handler does not depend on that.
- `year.<period>` rows: Include false → upsert `exclude.<period>` = 1.0; Include true → delete that key.
- `<scenario>.revenue` / `<scenario>.oe_margin` rows: for each Scenario present, both values blank → delete both keys (allowed for bear and bull; for base, rejected with "base Scenario is required"); exactly one blank → reject ("both year-5 revenue and margin are required"); both present → validate and upsert both keys.
- Validation: numbers only; revenue ≥ 0; margin between −100 and 100. Errors raise `ValueError`, which the existing route turns into HTTP 400 with the message.
- Unknown row ids are ignored; a body with no recognised rows is rejected.

### AI digest task
- New `AiTask` named `growth_digest`, one module in the AI tasks package, run with the existing `run_task` (same cache keyed on the latest 10-K accessions, same pending behaviour as One-line Answers).
- Result model: five list fields, each field's description being the category heading shown on the page: management guidance, segment growth, capacity expansions, market size, pricing. Each list item has a `finding` (one or two sentences) and `sources` (non-empty list of strings, each citing fiscal year and 10-K Item, e.g. "FY2025 10-K, Item 7 (MD&A)"). Empty lists are allowed.
- Instructions: read all years in the workspace, prefer the latest report for current facts, report only what the filings say (no outside estimates), quote numbers where the filings give them, cite every item.

## Testing Decisions

A good test exercises external behaviour: given statement data, saved inputs and a stubbed AI result, what the page shows and what a save stores. Tests do not assert on Table internals beyond the payload contract, on private helpers, or on template markup beyond visible text.

### Proposed seams (pending user confirmation)
1. **The sub-page over HTTP (primary).** GET and POST `/wizard/{ticker}/valuation/growth-estimation` through FastAPI's `TestClient`, with the adjusted statement set stubbed from the shared statement fixtures, a temporary wizard database, and `run_task` monkeypatched. Covers: history figures and CAGR availability, base-year notice, Reinvestment-implied Growth with and without exclusions ("k of 5"), saving and clearing exclusions, saving Scenarios, base-required and half-filled rejections, validation errors (HTTP 400), Scenario toggle fallback, digest pending vs ready, quarterly notice.
2. **Pure metrics functions (secondary, cheap).** `cagr`, historical n-year CAGR, Reinvestment Rate, Reinvestment-implied Growth with excluded and unavailable years, and Scenario Owner Earnings, tested with plain numbers. Edge cases: non-positive endpoints, fewer than n + 1 periods, k = 0, all years excluded, negative Owner Earnings.

### Modules tested
- Metrics module (new functions only; `roce.md` tests its own).
- Growth Estimation sub-page module (context builder, POST handler, Scenario loader) via seam 1.
- `growth_digest` task: every result field has a description (as One-line Answers does); answers parse from JSON.

### Prior art
- `tests/test_business_understanding.py`: `TestClient` page tests with `run_task` monkeypatched; pending vs ready.
- `tests/test_adjustments_engine.py`: pure formula tests (Owner Earnings with per-item maintenance).
- `tests/test_adjustments_post.py`: POST body validation and error cases.
- `tests/test_wizard_database.py`: temporary wizard database fixture.
- `tests/statement_fixtures.py`: StatementSet builders.

## Out of Scope

- Analyst consensus estimates as a dashboard source (future scope).
- Quarterly periods (future scope; annual only).
- A horizon other than five years, or a user-chosen horizon.
- Per-share figures and share-count projections (buybacks are Distributions).
- Live recompute of averages and Scenario figures while typing (refresh happens on save; see Assumptions).
- Defining the `valuation_inputs` schema, the price router, or the ROCE / After-tax Owner Earnings / Distributions / Retained Earnings functions (owned by `roce.md`).
- The Neff Ratio, Distributions yield and Target Neff (owned by `neff-ratio.md`).
- Human editing or correction of the AI digest; storing the digest anywhere but the AI cache.
- Segment-level or dimensional revenue history (see `specs/features/dimensional-breakdowns.md`).
- Probability weighting across Scenarios.

## Further Notes

- The base year is always the latest annual period; there is no picker.
- The Reinvestment-implied Growth window and the Scenario horizon share one constant (5) so they cannot drift.
- ROCE for the earliest cached period is unavailable by definition (no opening Net Assets in Use), so a company with exactly five cached years has at most four years with ROCE.

### Assumptions
1. Revenue is the income-statement row with standard concept `Revenue` (first non-dimensional match); added as a domain constant beside `PRETAX_INCOME`.
2. Owner Earnings per year is read from the Owner Earnings memo row of the fully adjusted statement set (all stages), not recomputed on this page. When the ticker has no saved owner_earnings preference, the page uses whatever `roce.md` defines for that case (unset maintenance % = 0) and does not solve it again.
3. History CAGRs are computed for revenue and Owner Earnings only, not for the margin.
4. n-year CAGR uses the latest period and the period n years earlier; it is unavailable with fewer than n + 1 periods or a non-positive endpoint.
5. Reinvestment-implied Growth = (mean ROCE over included years) × (mean Reinvestment Rate over included years), not the mean of yearly products.
6. The window is the latest five annual periods. Years with an unavailable ROCE or Reinvestment Rate are shown as unavailable and left out automatically (their checkbox is disabled), which also shrinks k.
7. Reinvestment Rate is unavailable when pre-tax Owner Earnings is ≤ 0.
8. Scenario CAGR is unavailable when base-year or year-5 Owner Earnings is ≤ 0; the page states why.
9. Year-5 revenue is typed in millions and stored in full currency units; margin is typed and stored as a percent, matching the maintenance % convention.
10. Validation: revenue ≥ 0; margin between −100 and 100; both Scenario fields required together; base cannot be cleared.
11. Excluded years are stored as `exclude.<period end date>` = 1.0; including a year deletes the key (absent = included, so the default is all ticked).
12. The Scenario toggle is a `scenario` query parameter read by the template (like One-line Answers' `view`); only the selected Scenario's form is rendered; no subpage-specific JavaScript.
13. All figures are computed server-side; the page reloads after a successful save via a new generic "reload after save" form option. The alternative (generic `div` / `pow` calculated-cell ops for live updates) was not chosen to keep one implementation of each formula.
14. The Scenario keys and a loader returning filled-in Scenarios live in this sub-page's module; `neff-ratio.md` imports the loader.
15. If `roce.md` provides no delete-by-key operation on `valuation_inputs`, this spec adds it.
16. The annual-only notice is one shared partial that does not exist yet; whichever grilled page is built first creates it.
17. The digest's AI pending state affects only the digest section, unlike One-line Answers where it replaces the whole page.
18. The digest result model is five lists of `{finding, sources[]}`; an empty list renders as "Nothing found in the filings".
