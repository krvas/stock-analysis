# Spec: Neff Ratio

- **Status:** ready for agent, not built
- **Depends on:** `owner-earnings-exceptional-items.md` (Owner Earnings excludes exceptional items), `roce.md` (`valuation_inputs` table, price router with manual override, market cap, Distributions metric), `growth-estimation.md` (Scenario inputs and their Owner Earnings CAGR)
- **Related docs:** `CONTEXT.md` (glossary), `specs/vision.md` (Page 5, Valuation → Neff Ratio), `specs/adjustments_architecture.md` §6 (metrics module), `specs/STATE.md` (hard rules; stale on implementation status)

## Problem Statement

After working out how fast a company might grow, the investor still has to answer "is the price right?". Today the Valuation page has only a placeholder Growth Estimation sub-page and nothing that sets the expected return against the price paid. The investor has to gather the Owner Earnings, the current market cap, the past dividends and buybacks and their own growth Scenarios by hand, then do the Neff arithmetic in a spreadsheet. They also cannot easily turn the question around ("what growth would this price need to be worth buying?").

## Solution

A new **Neff Ratio** sub-page on the Valuation page. It computes the Neff Ratio for each Scenario the investor filled in on Growth Estimation:

```
Neff Ratio = (Owner Earnings growth % + Distributions yield %) ÷ (market cap ÷ Owner Earnings)
```

Everything is whole-company and uses **pre-tax** Owner Earnings, so the "P/E" here is market cap ÷ pre-tax Owner Earnings. A note on the page says so.

- Growth % is the Scenario's Owner Earnings CAGR, as Growth Estimation computes it.
- The page shows past dividends and net buybacks per year. The investor enters **one** annual Distributions amount ($), shared by all Scenarios. Distributions yield = amount ÷ current market cap.
- The current price comes from the price router. If no price is available the investor can type one in (the manual override).
- **Target Neff** defaults to 1.5 and can be edited. The page also shows the inverse: the growth required to reach Target Neff.
- A toggle shows one Scenario at a time. Only Scenarios with saved inputs are offered.

Inputs are saved per ticker. The page is annual only.

## User Stories

1. As the investor, I want a Neff Ratio sub-page on the Valuation page, so that pricing sits next to Growth Estimation in the wizard.
2. As the investor, I want the Neff Ratio worked out for me from figures the wizard already has, so that I don't rebuild them in a spreadsheet.
3. As the investor, I want the Neff Ratio to use pre-tax Owner Earnings, so that it is on the same basis as the rest of the wizard (ROCE, Growth Estimation).
4. As the investor, I want a note saying the P/E on this page is on pre-tax Owner Earnings, so that I don't compare it with a reported P/E and think it is cheap.
5. As the investor, I want whole-company figures (market cap and total Owner Earnings), not per-share figures, so that buybacks are counted once, as Distributions, and not again through a falling share count.
6. As the investor, I want only the Owner Earnings variant (no reported-EPS variant), so that the page has one answer I trust.
7. As the investor, I want the Owner Earnings used to be the latest annual period's pre-tax Owner Earnings, so that it matches the base year Growth Estimation grows from.
8. As the investor, I want to see the current market cap and how it was built (price × shares outstanding), so that I can check it.
9. As the investor, I want the current price fetched for me, so that I don't have to look it up.
10. As the investor, I want to see the date of the price used, so that I know how fresh it is.
11. As the investor, I want to type a price when no provider can give one, so that the page still works when the free API limits are used up.
12. As the investor, I want the price I typed to be remembered with its date, so that I don't retype it on every visit.
13. As the investor, I want to see market cap ÷ Owner Earnings (the pre-tax P/E), so that I can see the price multiple directly.
14. As the investor, I want the Owner Earnings growth % taken from the Scenario's CAGR on Growth Estimation, so that I enter my growth views in one place only.
15. As the investor, I want a toggle that shows one Scenario (bear, base or bull) at a time, so that the page stays readable.
16. As the investor, I want the toggle to offer only Scenarios I have filled in, so that I never see an empty Scenario.
17. As the investor, I want the base Scenario selected by default when it is filled in, so that I see my central case first.
18. As the investor, I want a clear message and a link to Growth Estimation when I haven't filled in any Scenario, so that I know what to do next.
19. As the investor, I want past dividends, net buybacks and total Distributions for every cached year, so that I can judge a sensible annual Distributions amount.
20. As the investor, I want net buybacks shown as repurchases minus stock issued, so that dilution from stock issuance reduces what I count as returned.
21. As the investor, I want to enter one annual Distributions amount in dollars, so that I set my own expectation instead of trusting one past year.
22. As the investor, I want that one amount to apply to every Scenario, so that the Scenarios differ only in growth.
23. As the investor, I want the Distributions yield (amount ÷ current market cap) shown, so that I see what my amount means against the price.
24. As the investor, I want an unset Distributions amount to count as zero and the page to say so, so that the Neff Ratio is never quietly inflated.
25. As the investor, I want a Target Neff that defaults to 1.5, so that I start from a sensible bar.
26. As the investor, I want to change the Target Neff and have it saved, so that I can use my own bar for this company.
27. As the investor, I want to see the growth required to reach Target Neff, so that I can ask whether that growth is plausible.
28. As the investor, I want growth required to show even when I haven't filled in a Scenario, so that I can reason backwards before I build Scenarios.
29. As the investor, I want the Neff Ratio shown next to the Target Neff, so that I can see at a glance whether the price clears my bar.
30. As the investor, I want the page to show the parts of the ratio (growth %, yield %, P/E), so that I see which part drives the result.
31. As the investor, I want my Distributions amount and Target Neff saved per ticker, so that they are still there when I come back.
32. As the investor, I want the page to refresh its results after I save, so that what I see matches my inputs.
33. As the investor, I want a clear error when I type something that isn't a number, so that bad input is never saved.
34. As the investor, I want a Target Neff of zero or below to be rejected, so that the inverse calculation stays meaningful.
35. As the investor, I want to be able to enter a negative Distributions amount for a company that issues more stock than it buys back, so that net dilution counts against the return.
36. As the investor, I want the page to refuse the Neff Ratio and say why when base-year Owner Earnings are zero, negative or missing, so that I never see a meaningless multiple.
37. As the investor, I want the page to say "price unavailable" and still show the price entry when no price can be found, so that I can carry on.
38. As the investor, I want the page to say which figure is missing when shares outstanding cannot be found, so that I know why there is no market cap.
39. As the investor, I want a Scenario whose CAGR cannot be computed to say why, instead of showing a number, so that I am not misled.
40. As the investor, I want the quarterly view to show an "annual only" notice, so that I know this page works on annual figures.
41. As the investor, I want the figures here to match the Owner Earnings, Distributions and market cap shown on ROCE and Growth Estimation, so that the wizard agrees with itself.
42. As the investor, I want visiting this page not to use up my free price API quota, so that it stays usable through the day (the price router's caching and call counting handle this).

## Implementation Decisions

### Definitions (formulas)

All percentages are in percentage points (15 means 15%).

- **Owner Earnings (OE)**: pre-tax Owner Earnings of the latest annual period, after all adjustments and excluding exceptional items. This is the same figure and base year Growth Estimation uses. It is obtained the way roce.md defines for the metrics, including when no owner_earnings preferences are saved.
- **Market cap** = current price × shares outstanding, as roce.md defines it (price router current price, or the manual override; EDGAR cover-page share count of the latest 10-K).
- **P/E (pre-tax)** = market cap ÷ OE. Only defined when OE > 0 and market cap is known.
- **Distributions yield %** = 100 × Distributions amount ÷ market cap.
- **Growth %** = the selected Scenario's Owner Earnings CAGR from the base year to year 5, as growth-estimation.md computes it, expressed in percentage points.
- **Neff Ratio** = (growth % + Distributions yield %) ÷ P/E.
- **Growth required %** = Target Neff × P/E − Distributions yield %. It does not depend on any Scenario.

### Modules

- **Pure metrics module (adjustments package).** Add two pure functions next to the shared metrics that roce.md and growth-estimation.md define:
  - Neff Ratio from (growth %, Distributions yield %, P/E).
  - Growth required from (Target Neff, P/E, Distributions yield %).
  Both return "undefined" (no number) when P/E is not defined. Reuse the module's existing Distributions function (roce.md), market cap function (roce.md) and Scenario CAGR function (growth-estimation.md). Do not redefine any of them.
- **Neff Ratio sub-page module (wizard pages).** A new subpage-specific module that holds the context builder and the POST handler, and owns this page's constants: the subpage key, the input keys, the default Target Neff of 1.5, and the Scenario order bear, base, bull. Per the repo rule, none of this goes into shared files.
- **Wizard registry.** Add a `neff-ratio` sub-page ("Neff Ratio", order 2) under the Valuation page, pointing at the new builder and handler. Identity only.
- **Template.** A new template for the sub-page under the Valuation template folder.

### Stored inputs (`valuation_inputs`, defined in roce.md)

Use roce.md's table and its database manager methods. This page adds these rows, with `subpage = 'neff-ratio'`:

| input_key | meaning | default when absent |
| --- | --- | --- |
| `target_neff` | Target Neff | 1.5 |
| `distributions_amount` | annual Distributions amount in dollars, shared by all Scenarios | 0 (page says "not entered, counted as 0") |

- Scenario inputs are read with growth-estimation.md's keys and read path. This page never writes them.
- The price override is roce.md's (stored with its date). This page shows roce.md's price entry when the price router has no price. It does not define its own price key.
- No migrations: the table is defined once in the wizard schema file (roce.md).

### Context builder

Signature `(ticker, period)`, like every builder. It returns:

- An **annual-only flag** when `period` is quarterly. The template then shows only the shared "annual only" notice partial.
- **Price block**: price, its date, its source (provider or manual), shares outstanding, market cap, or a "price unavailable" state with roce.md's override entry.
- **Owner Earnings block**: base year label, OE, P/E, or a refusal reason (OE missing, zero or negative; shares missing).
- **Distributions history**: a serialized `Table` with one column per cached annual year (newest first) and the rows Dividends, Net buybacks and Distributions, from the Distributions metric. Static cells only.
- **Inputs table**: a serialized `Table` with rows `distributions_amount` and `target_neff` and one input column `value` (number), filled with the saved values or the defaults. This is the same input and save pattern as Owner Earnings: the form posts `model.serialize()`.
- **Derived values for the saved inputs**: Distributions yield %, growth required %, and whether the amount is unset.
- **Scenarios**: a list in the order bear, base, bull, with only the Scenarios that have saved inputs. Each entry has its name, growth % (or the reason it is undefined), Neff Ratio (or the reason it is undefined), and whether it meets Target Neff (Neff Ratio ≥ Target Neff).

The builder does all the arithmetic in Python through the pure functions. No Neff math runs in JS.

### Scenario toggle

A GET select (`?scenario=bear|base|bull`) that reloads the page, the same mechanism as the One-line Answers view switch. The template picks the entry to show from the list: the requested Scenario if it is filled in, otherwise base, otherwise the first filled one. When the list is empty, the template shows a message linking to Growth Estimation, and still shows the inputs, the P/E, the yield and growth required.

### POST handler

The body is `{rows: [{id, cells: {value}}]}` from the inputs table.

- `distributions_amount`: must be a finite number; negative is allowed. Blank is stored as 0.
- `target_neff`: must be a finite number > 0. Blank is stored as 1.5.
- Unknown row ids are ignored. A body with no known rows is rejected (`ValueError`, which becomes HTTP 400, as in the existing handlers).
- Upsert into `valuation_inputs` with ticker, the default exchange, `subpage = 'neff-ratio'` and the input key. Return `{ok, rows_written}`.

### Refresh after save

Results are server-computed, so they must be re-rendered after a save. Add a generic, opt-in "reload after successful save" attribute to the wizard save form macro and the generic save wiring. Any sub-page could use it, so it passes the shared-file test in CLAUDE.md. Only this page turns it on.

### Page copy

- Formula line: `Neff Ratio = (Owner Earnings growth % + Distributions yield %) ÷ (market cap ÷ Owner Earnings)`.
- Pre-tax note: the P/E here is market cap ÷ pre-tax Owner Earnings, so it reads lower than a reported P/E, which is on after-tax net income.
- Inverse line: `Growth required = Target Neff × P/E − Distributions yield %`.

## Testing Decisions

A good test checks behaviour you can see from outside: the context a GET renders (values, refusal messages, which Scenarios are offered) and what a POST stores or rejects. Tests do not check private helpers or the shape of the template's markup beyond the visible values. No network access: stub the price router, the adjusted-statement load and the Scenario read at the module boundary, as the existing wizard tests do.

### Proposed seams (pending user confirmation)

1. **Primary: the Neff Ratio sub-page through the app (context builder + POST handler).** Use `TestClient` GET/POST on `/wizard/{ticker}/valuation/neff-ratio`, with a temporary wizard DB and stubbed price router, Owner Earnings and Scenario sources. This one seam covers:
   - the formulas end to end
   - defaults (Target Neff 1.5, Distributions 0 with its note)
   - Scenario filtering and toggle fallback
   - refusal states (OE ≤ 0, price unavailable, shares missing, undefined CAGR)
   - the annual-only notice
   - POST validation and persistence, including a GET after a POST returning the saved values
2. **Secondary, optional: the two pure functions in the metrics module.** Direct unit tests, but only for numeric edge cases that are awkward to reach through the page (for example, P/E undefined leading to no result). Drop this seam if the primary one covers those cases.

### Prior art

- `tests/test_balance_sheet_size.py`: builder and page tests through `TestClient`, with monkeypatched statement loading.
- `tests/test_business_understanding.py`: page states, including a toggle driven by a query parameter.
- `tests/test_adjustments_post.py`: POST body validation.
- `tests/test_wizard_database.py`: wizard DB round trips against a temporary database.

## Out of Scope

- Quarterly periods (the page shows an "annual only" notice; quarterly is future scope across all five pages).
- Bond as a Business (1/PE against the AAA bond yield). It is a separate future sub-page.
- A per-share Neff Ratio, a reported-EPS variant, or an after-tax Owner Earnings variant.
- A Distributions amount per Scenario (one amount is shared by design).
- Entering or editing Scenario inputs on this page (Growth Estimation owns them).
- Defining or changing the price router, its providers, caching, call counting or the manual override's storage (roce.md owns these).
- Defining `valuation_inputs`, the Distributions metric or the market cap calculation (roce.md), or the Scenario CAGR (growth-estimation.md).
- Neff Ratio history or a trend over past years (it would need historical prices and Scenarios).
- Live recalculation while typing (results refresh after save).
- Analyst consensus growth (future scope in growth-estimation.md).

## Further Notes

### Assumptions

- When the ticker has no saved owner_earnings preferences, the owner_earnings adjustment does not run. roce.md defines how the metrics still get Owner Earnings in that case (unset maintenance % = 0). This page reuses that definition and does not solve it again.
- The "annual only" notice is a shared partial that does not exist yet. Whichever grilled page lands first creates it, and this page includes it.
- The Owner Earnings in the Neff Ratio is the latest annual period's pre-tax Owner Earnings, the same base year as Growth Estimation. No trailing-twelve-month figure is used, because the page is annual only.
- Percentages are percentage points throughout, so Neff = (15 + 3) ÷ 12 = 1.5.
- An unset Distributions amount counts as 0, and the page shows a note. A blank POST value is stored as 0. The default is not prefilled from history.
- A blank Target Neff in a POST is stored as 1.5, so the handler never needs a delete path.
- A negative Distributions amount is allowed (net issuer). Target Neff must be > 0.
- The two Neff functions live in the shared pure metrics module, next to Distributions, ROCE and the other metrics, not in the sub-page module. They are pure domain formulas.
- roce.md's Distributions metric exposes `dividends`, `repurchases` and `stock_issued` per period as well as their combined `distributions`; the history table shows dividends and net buybacks (repurchases − stock issued) from those columns.
- The Scenario toggle is a GET query parameter that reloads the page (the One-line Answers view-switch pattern). The context builder returns all filled Scenarios and the template chooses one, so the builder signature `(ticker, period)` is unchanged.
- The default Scenario is base if filled, otherwise the first filled one in the order bear, base, bull.
- "Meets Target Neff" means Neff Ratio ≥ Target Neff.
- Results are computed server-side. A generic, opt-in "reload after successful save" form attribute is added to the shared save macro and wiring, instead of live calculated cells. The existing calculated-cell expressions support only add and mul, and the Scenario panels are server-rendered.
- The Distributions history table covers every cached annual year, newest first.
- Growth required is shown even when no Scenario is filled in, because it does not depend on one.
- The `valuation_inputs` subpage value for this page is `neff-ratio` (the sub-page slug). The input keys are `target_neff` and `distributions_amount`.
- When the price router has no price, this page uses roce.md's manual price entry. It adds no price input of its own.
