# Spec: ROCE and the Retained Earnings Test

- **Status:** ready for agent, not built
- **Depends on:** `owner-earnings-exceptional-items.md` (Owner Earnings excludes exceptional items), `assets-in-use.md` (the `assets_in_use` adjustment type and its Net Assets in Use memo row)
- **Depended on by:** `growth-estimation.md` (ROCE, Retained Earnings, `valuation_inputs`), `neff-ratio.md` (price router, Distributions, `valuation_inputs`)
- **Related docs:** `CONTEXT.md` (glossary), `specs/adjustments_architecture.md` §2, §6, §8 (pipeline, `metrics` module, stage semantics), `specs/STATE.md` (stale; trust the code), `CLAUDE.md` (shared-file rule)

This spec also owns three cross-cutting pieces that later specs reuse: the `valuation_inputs` table, the price router, and the first functions of the shared metrics module (After-tax Owner Earnings, Distributions, Retained Earnings, ROCE).

## Problem Statement

The investor has adjusted a company's statements to get Owner Earnings and Net Assets in Use, but the wizard never turns them into a return figure. They cannot see how much the business earns on the capital it actually uses (ROCE), and they cannot check whether the earnings the business kept turned into market value (the Retained Earnings Test). Doing it by hand means copying adjusted numbers out of several pages, looking up tax, dividends, buybacks and share counts in the filings, and finding historical share prices from a price site. The app also has no place to store a numeric human input that is not an adjustment (such as the N-year window or a typed price), and no shared way to get a share price within free API limits.

## Solution

A new **ROCE** sub-page on the Business Quality page shows, for every recent annual period:

- ROCE: Owner Earnings divided by the average of opening and closing Net Assets in Use. The oldest cached period has no opening balance, so it has no ROCE. No unadjusted ROCE is shown.
- The Retained Earnings Test over the last N years (default 5, editable): change in market cap over the window divided by the sum of Retained Earnings over the same years. The page shows the full build-up: Owner Earnings, reported income tax, After-tax Owner Earnings, dividends, repurchases, stock issued, Distributions, Retained Earnings per year; and both market caps with their price, price date, price source and cover-page share count.

Prices come from a shared price router that uses the existing Finnhub and Alpha Vantage clients, stays within their free tiers, and caches results. When no price is available the page says "price unavailable" and the investor can type one; a typed price is stored with its date.

If Owner Earnings cannot be computed for any year in the window, the test refuses and names the year. `period=quarterly` shows only an "annual only" notice.

## User Stories

1. As the investor, I want a ROCE sub-page on the Business Quality page, so that I can judge returns right after judging Moats.
2. As the investor, I want ROCE computed from Owner Earnings, so that the numerator matches the earnings I built on the Adjustments pages.
3. As the investor, I want the ROCE numerator to be pre-tax Owner Earnings after all adjustments and excluding exceptional items, so that one-off gains or losses don't distort returns.
4. As the investor, I want the ROCE denominator to be the average of opening and closing Net Assets in Use, so that capital added during the year is counted fairly.
5. As the investor, I want the oldest cached year to show no ROCE, so that the page never invents an opening balance.
6. As the investor, I want no unadjusted ROCE on the page, so that I am not tempted to anchor on a number I have already decided is wrong.
7. As the investor, I want to see Owner Earnings, opening and closing Net Assets in Use and their average next to each ROCE value, so that I can check the arithmetic.
8. As the investor, I want ROCE shown as a percentage for each annual period, newest first, so that I can see the trend.
9. As the investor, I want a year whose average Net Assets in Use is zero or negative to show "n/m" rather than a huge or negative ratio, so that I'm not misled.
10. As the investor, I want a year where Owner Earnings or Net Assets in Use is missing to show a blank cell with a reason, so that I know why ROCE is missing.
11. As the investor, I want ROCE to use my saved % in use and liability netting choices, so that the denominator reflects my judgment on the Assets in Use page.
12. As the investor, I want ROCE to work even if I never saved anything on the Owner Earnings page, so that unset maintenance % counts as 0% as it does elsewhere.
13. As the investor, I want ROCE to work even if I never saved anything on the Assets in Use page, so that the defaults (100% in use, nothing netted) apply.
14. As the investor, I want the Retained Earnings Test on the same sub-page, so that both capital-efficiency checks sit together.
15. As the investor, I want the test defined as (market cap now − market cap N years ago) ÷ Σ Retained Earnings over those N years, so that I see the value created per dollar retained.
16. As the investor, I want N to default to 5, so that I get a sensible answer without typing anything.
17. As the investor, I want to change N and have it remembered for this ticker, so that I don't retype it every visit.
18. As the investor, I want the page to reject an N that is not a whole number of at least 1, so that the test is always well defined.
19. As the investor, I want the page to tell me when there are not enough cached years for my N, and how many there are, so that I can lower N.
20. As the investor, I want Retained Earnings per year defined as After-tax Owner Earnings minus Distributions, so that growth spending capitalized by my adjustments (e.g. brand advertising) counts as retained.
21. As the investor, I want After-tax Owner Earnings to subtract the reported income tax expense, not a computed tax rate, so that the figure ties to the filing.
22. As the investor, I want Distributions to be dividends plus net buybacks (repurchases minus stock issued), so that a buyback is treated like a dividend.
23. As the investor, I want dividends, repurchases and stock issued shown as separate rows, so that I can see what drove Distributions.
24. As the investor, I want dividends to non-controlling interests excluded from Distributions, so that only cash to the company's own shareholders counts.
25. As the investor, I want a year with no dividend or buyback line to count those as zero, so that a company that pays nothing is handled correctly.
26. As the investor, I want the test to refuse and name the year when Owner Earnings cannot be computed for a year in the window (e.g. pretax income is missing), so that I never get a silently wrong ratio.
27. As the investor, I want the test to refuse and name the year when reported income tax is missing for a year in the window, so that After-tax Owner Earnings is never guessed.
28. As the investor, I want market cap computed as price × cover-page shares outstanding of the relevant 10-K, so that the share count comes from EDGAR, not a price API.
29. As the investor, I want the "now" market cap to use today's price and the latest 10-K's cover-page share count, so that it is current.
30. As the investor, I want the "N years ago" market cap to use the month-end close at the start of the window and the share count of the 10-K for the year that ended then, so that both figures refer to the same moment.
31. As the investor, I want the page to show each market cap's price, price date, price source and share count with its cover-page date, so that I can verify them.
32. As the investor, I want companies with several share classes to use the total of all classes on the cover page, so that market cap isn't understated.
33. As the investor, I want historical prices that are not split-adjusted, so that price × the share count of that time gives the real market cap.
34. As the investor, I want the test shown as a ratio with a plain sentence ("each $1 retained created $X of market value"), so that it is easy to read.
35. As the investor, I want a negative or zero Σ Retained Earnings to show "n/m" with the reason, so that a division by a non-positive retained amount isn't presented as a result.
36. As the investor, I want the per-year build-up table to cover exactly the N years in the window, so that the sum I see is the sum used.
37. As the investor, I want current prices fetched automatically, so that I don't have to look them up.
38. As the investor, I want historical month-end closes fetched automatically, so that I don't have to look them up.
39. As the investor, I want the app to never exceed the free API limits, so that I'm not blocked or billed.
40. As the investor, I want a current price reused for the rest of the day, so that reloading the page doesn't spend API calls.
41. As the investor, I want historical closes cached permanently, so that a past price is fetched only once ever.
42. As the investor, I want the router to prefer the provider with generous rate limits when it supports the ticker, and fall back to the other, so that scarce calls are saved.
43. As the investor, I want to see "price unavailable" when both providers fail or are out of calls, so that I know why a figure is missing.
44. As the investor, I want to type a price when it is unavailable, so that I can still finish the test.
45. As the investor, I want to override a fetched price, so that I can correct a bad quote.
46. As the investor, I want a typed price stored with its date, so that I know how old it is.
47. As the investor, I want a typed historical close to be reused whenever the window starts on that date, so that I enter it once.
48. As the investor, I want a typed current price to apply only on the day I typed it, so that a stale price doesn't silently persist.
49. As the investor, I want clearing a typed price to go back to the fetched price, so that overrides are reversible.
50. As the investor, I want the page labelled with the price source ("Finnhub", "Alpha Vantage", "manual"), so that I know where each price came from.
51. As the investor, I want the page to recompute after I save N or a price, so that I see the new result right away.
52. As the investor, I want `period=quarterly` to show an "annual only" notice, so that I don't mistake annual figures for quarterly ones.
53. As the investor, I want the same Owner Earnings, After-tax Owner Earnings, Distributions, Retained Earnings and ROCE numbers on later pages (Growth Estimation, Neff Ratio), so that the wizard never contradicts itself.
54. As the investor, I want a short intro on the page explaining ROCE, the Retained Earnings Test and why Retained Earnings starts from Owner Earnings rather than net income, so that I remember the reasoning.
55. As the investor, I want the share count source and the formulas shown on the page, so that the method is visible.
56. As the investor (as developer of later pages), I want one store for numeric human inputs that are not adjustments, so that Scenario inputs, excluded years, Target Neff and the Distributions amount don't each need a new table.
57. As the investor (as developer of later pages), I want one price interface with "current price" and "month-end close on a date", so that the Neff Ratio page reuses it unchanged.
58. As the investor (as developer of later pages), I want the price manual-override rule in one place, so that ROCE and Neff Ratio treat typed prices identically.
59. As the investor (as developer), I want the provider free-tier facts verified and recorded before the router is built, so that limits are real, not remembered.
60. As the investor (as developer), I want the router testable with fake providers, so that tests never call the live APIs.

## Implementation Decisions

### Shared metrics module (new, inside the adjustments package)

Pure functions over an adjusted `StatementSet`; no I/O. Each returns a per-period series (period label → value, newest first) with periods that cannot be computed left out. This is the `metrics` module planned in `specs/adjustments_architecture.md` §6; later specs add Reinvestment Rate here.

- `owner_earnings(ss)`: values of the Owner Earnings memo row on the cash-flow statement inserted by the `owner_earnings` adjustment type. The type module exposes that row's concept as a constant (today it is a literal inside `apply`); the metrics module imports it rather than repeating the string. Whatever `owner-earnings-exceptional-items.md` changes about the formula flows through automatically.
- `income_tax_expense(ss)`: reported income tax expense from the **income statement** (non-dimensional row with `standard_concept` `IncomeTaxes`; raw sign, expense positive). The cash-flow statement also carries `IncomeTaxes` rows (taxes paid, deferred tax) and must not be used.
- `after_tax_owner_earnings(ss)` = `owner_earnings − income_tax_expense`, only for periods with both values. No computed tax rate.
- `distributions(ss)`: per period, columns `dividends`, `repurchases`, `stock_issued`, `distributions`, where `distributions = dividends + repurchases − stock_issued` (all as positive cash amounts). Matched by **concept QName**, not `standard_concept` (verified in the cache: edgartools maps `PaymentsOfDividends` to `DistributionsToMinorityInterests` and `PaymentsOfDividendsCommonStock` to `NetCashFromFinancingActivities`, so standard labels are unusable). For each component, an ordered concept list; per period take the first concept in the list that has a value (filers switch concepts between years, e.g. COST uses `PaymentsOfDividends` before FY2022 and `PaymentsOfDividendsCommonStock` after), so totals are never double counted. A component with no matching value in a period is 0. Starting lists (the implementer may extend them after checking cached tickers; they live as named constants with the other edgartools term names):
  - dividends: `us-gaap_PaymentsOfDividendsCommonStock`, `us-gaap_PaymentsOfDividends`
  - repurchases: `us-gaap_PaymentsForRepurchaseOfCommonStock`, `us-gaap_PaymentsForRepurchaseOfEquity`
  - stock issued: `us-gaap_ProceedsFromIssuanceOfCommonStock`, `us-gaap_ProceedsFromIssuanceOrSaleOfEquity`, `us-gaap_ProceedsFromStockOptionsExercised`
  - never: `us-gaap_PaymentsOfDividendsMinorityInterest` (non-controlling interests).
- `retained_earnings(ss)` = `after_tax_owner_earnings − distributions`, per period with both.
- `net_assets_in_use(ss)`: values of the Net Assets in Use memo row (`adj_NetAssetsInUse`) on the balance sheet inserted by the `assets_in_use` type (concept constant exported by that type module, owned by `assets-in-use.md`).
- `roce(ss)`: for each period t that has a prior cached period t−1: `ROCE_t = OE_t ÷ ((NAIU_t + NAIU_{t−1}) / 2)`. Left out when either NAIU or OE is missing; marked not meaningful when the average is ≤ 0 (the function returns NaN for those so the page can label them "n/m"; the oldest period is simply absent).

### Getting a fully adjusted set with defaults

Today a type only runs when a spec exists, and specs come only from saved prefs, so a ticker with no saved `owner_earnings` prefs has no Owner Earnings row. `assets-in-use.md` defines the mechanism that fixes this: a generic "applies by default" declaration on an adjustment type, honoured by the specs builder, so the type runs with empty params when no prefs are saved (`assets_in_use` uses it, so the `adj_NetAssetsInUse` memo row is always on the adjusted balance sheet). Decision:

- The `owner_earnings` type declares that it applies by default, using that same mechanism (no second mechanism). With empty params every maintenance % is 0, matching the existing "unset = 0" behaviour.
- Consequence: the Owner Earnings memo rows now appear on the adjusted statement view for every ticker, not only tickers with saved prefs. That is intended.
- Metric consumers (ROCE, Growth Estimation, Neff Ratio) use the existing `load_adjusted(ticker, "annual")` with no `until`, i.e. the fully adjusted set. No new loader.

### Cover-page shares outstanding (EDGAR)

The edgartools cache does not hold the cover-page share count today. Add it:

- At cache build, for each annual filing read `dei:EntityCommonStockSharesOutstanding` from the filing's XBRL facts (prior art: the note-fact reader that builds the D&A breakdown). Value = the undimensioned fact if present, else the sum of the per-class dimensioned facts (multi-class companies report one per class). Keep the fact's date (cover-page "as of" date).
- Store it per bundle as a small extra cached frame (`period` = fiscal period label of that 10-K, `shares_outstanding`, `as_of`), bump the cache schema version, and expose it through the edgartools source module as a read function for a ticker (annual only). It is not inserted into any statement, so statement views and the engine are untouched.

### Retained Earnings Test (ROCE sub-page module)

A pure function in the ROCE sub-page module (only this page uses it) takes the per-period metric series, cover-page shares, N, and two resolved prices, and returns either a result or a refusal.

- Window: the latest N annual periods `t_1 … t_N` (newest first). Start of window = fiscal year end of the period just before the window, `t_{N+1}`. Requires N+1 cached annual periods (N years of Retained Earnings plus the start-of-window share count); otherwise refuse with "only K annual reports cached; N can be at most K−1".
- Refusals (each names the year or years): Owner Earnings missing for a year in the window; income tax expense missing for a year in the window; cover-page shares missing for the latest 10-K or the start-of-window 10-K; a price unavailable (the refusal is "price unavailable", shown next to the price input).
- `market_cap_now = current_price × shares(t_1)`.
- `market_cap_start = month_end_close(start_date) × shares(t_{N+1})`, where the month-end close is the close on the last trading day of the calendar month containing the fiscal year end of `t_{N+1}`.
- `test = (market_cap_now − market_cap_start) ÷ Σ_{i=1..N} RetainedEarnings(t_i)`. If the sum is ≤ 0, result is "n/m" with the reason.
- Result also carries every intermediate (per-year build-up, both prices with date and source, both share counts with their as-of dates) for display.

### ROCE sub-page

- Registry: new sub-page on the `business-quality` page, slug `roce`, title "ROCE", order 2 (after Moats), with a context builder and a POST handler from a new `wizard_pages` module. Registry entry is identity only.
- Context builder:
  - `period != "annual"`: return only the annual-only flag; the template renders the shared "annual only" notice partial and nothing else. That partial does not exist yet; **whichever grilled page lands first creates it** as a generic wizard partial and the others include it.
  - Otherwise: load the fully adjusted annual set (above), compute the metric series, read N and price overrides from `valuation_inputs`, resolve prices (below), run the Retained Earnings Test.
  - Serializes three static `Table`s (Table payload contract; row ids are fixed keys for computed rows):
    1. ROCE table: rows Owner Earnings, Opening Net Assets in Use, Closing Net Assets in Use, Average Net Assets in Use, ROCE %; columns = the latest `HISTORY_YEARS` annual periods (existing config value, 10).
    2. Retained Earnings build-up: rows Owner Earnings, Income tax expense, After-tax Owner Earnings, Dividends, Repurchases, Stock issued, Distributions, Retained Earnings; columns = the N window years; a Σ column for Retained Earnings.
    3. Inputs table (the only one with input cells): rows `n_years`, `price_now`, `price_start`, one numeric input column; static columns show the fetched price, its date and source, and the start date. Blank price inputs mean "use the fetched price".
  - Plus a result block: both market caps, Δ market cap, Σ Retained Earnings, the test ratio and its sentence, or the refusal message.
- POST handler: body is the inputs table's `TableModel.serialize()` (existing save flow, one table per form). Validates N as an integer ≥ 1 (and ≤ cached annual periods − 1), prices as numbers > 0. Writes N under the ROCE sub-page's inputs. Writes `price_now` as the current-price override; writes `price_start` as the historical override for the start date computed from the **submitted** N (the handler reads cached annual periods to get it). A blank price deletes that override. Returns `{"ok": true, ...}`; errors raise `ValueError` → 400 as today.
- After a successful save the page reloads so the server-computed result reflects new inputs. This is a generic opt-in on the wizard save form (a data attribute read by the save wiring, meaning "reload after save"); it contains no sub-page knowledge, so it is allowed in the shared wiring file.
- Template: intro (formulas for ROCE, After-tax Owner Earnings, Distributions, Retained Earnings, the test; the GEICO rationale for starting from Owner Earnings), the three tables, result block, and the share-count source note.

### `valuation_inputs` table (wizard DB)

- New table in the wizard schema: `ticker VARCHAR`, `exchange VARCHAR`, `subpage VARCHAR`, `input_key VARCHAR`, `value DOUBLE NOT NULL`, `updated_at TIMESTAMP NOT NULL`, primary key `(ticker, exchange, subpage, input_key)`. No surrogate id. Table constants (name, columns, unique key) added to the wizard tables module like `adjustment_preferences`.
- Ticker and exchange are upper-cased on write and read; exchange is the existing web-layer default exchange.
- `subpage` is a namespace: a wizard sub-page slug (`roce`, later `growth-estimation`, `neff-ratio`) or the shared namespace `price` for price overrides, which both ROCE and Neff Ratio read.
- `WizardDatabaseManager` gains: upsert (conflict on the primary key updates `value` and `updated_at`), read for a ticker+exchange (optionally one namespace), and delete by key list of `(ticker, exchange, subpage, input_key)` (no-op on empty list or unknown keys; case-insensitive ticker/exchange like the existing preferences delete). Delete-by-key is used here to clear a typed price and by `growth-estimation.md` to re-include an excluded year. Schema bootstrap checks every table in the wizard tables list, not just `adjustment_preferences`, so an existing DB gains the new table (the DDL is `CREATE TABLE IF NOT EXISTS`; resetting the DB is also fine, there are no migrations).
- Keys this spec writes:
  - namespace `roce`: `n_years` (default 5 when absent).
  - namespace `price`: `current` (typed current price; its date is `updated_at`'s date), `month_end_close:<YYYY-MM-DD>` (typed close for that month-end date; the date is in the key).

### Price router (new provider-agnostic module in the API package)

Interface (generic, reused by Neff Ratio):

- `current_price(ticker) -> PriceResult`
- `month_end_close(ticker, on: date) -> PriceResult` — close on the last trading day of the calendar month containing `on`, **not split-adjusted**.
- `PriceResult`: either a price (`value`, `as_of` date, `source` = provider name) or unavailable (`reason`: unsupported ticker, limit reached, provider error, no data).

Behaviour:

- Two provider adapters wrap the existing Finnhub and Alpha Vantage clients; each declares which request kinds it can serve on the free tier (from the verified-facts table). The clients gain only thin fetch methods they lack (e.g. a quote endpoint for Alpha Vantage, a monthly or daily series endpoint), called with the clients' own disk cache **off**: the router owns caching, because the existing client cache never expires (the Finnhub quote cache would serve a stale price forever).
- Order: the provider with ticker restrictions but generous rate limits first, when it supports the request kind and has calls left; then the all-ticker provider. Which provider is which is taken from the verified facts, not assumed.
- A provider answer that means "this ticker/endpoint is not on your plan" marks that (provider, ticker, kind) unsupported for the day and falls through. A rate-limit answer (Alpha Vantage returns 200 with a `Note`/`Information` body) marks the provider exhausted for the day.
- Local call counting: per provider, per day (in the provider's reset timezone, from the facts) and per minute if the provider has a minute limit. A call is refused locally before the limit is hit. Counts persist in a small JSON state file under the data directory so restarts don't reset them.
- Caching (router-level, provider-agnostic, under the data directory): current price cached for the rest of the calendar day; month-end closes cached permanently, keyed by ticker and month-end date. Cache entries record the source.
- Never raises to callers for provider problems; returns unavailable.

Manual override resolution (web layer, one shared helper beside the adjusted-statements loader, used by ROCE and later Neff Ratio): read namespace `price` from `valuation_inputs`; a `month_end_close:<date>` override always wins for that date; a `current` override wins only if its `updated_at` date is today, otherwise the router is asked and, if it is unavailable, the page shows "price unavailable" with the old typed value and its date pre-filled. Result source is `manual` when an override wins.

### Implementer's first step: verify the providers' free tiers

Before writing the router, the implementing worker researches both providers' **current** free tiers from their official docs/pricing pages (and, if keys are in `.env`, at most a handful of live probe calls) and records a verified-facts table in the router module's docstring (date checked, source URL per row). It must cover, per provider:

1. Daily and per-minute call limits on the free tier, and when the daily counter resets (timezone).
2. Which tickers/exchanges are free (expected shape to confirm or refute: one provider limits tickers but has generous limits; the other covers all tickers with restrictive limits).
3. Whether a current-quote endpoint is free, its name, and what "as of" timestamp it returns.
4. Whether any historical endpoint that reaches back at least 15 years is free (e.g. monthly series, full daily history, candles), its name, and how far back it goes.
5. Whether that historical endpoint's close is split-adjusted, dividend-adjusted, or raw. Only a raw (not split-adjusted) close may be used for `month_end_close`; an endpoint that only gives adjusted closes is recorded as unusable for it.
6. What an "over limit" response and a "not on your plan" response look like (HTTP status, body), so the router can tell them apart.

The router's limits and capability flags are constants derived from that table (in the central config module), so a plan change is a one-place edit.

## Testing Decisions

A good test drives a module only through its public interface with realistic inputs and asserts on observable outputs (values, refusals, what was stored, which provider was called and how often). No assertions on private helpers, DataFrame internals, or call order beyond what the behaviour requires. No live API calls and no real SEC data in the default suite.

### Proposed seams (pending user confirmation)

1. **Metrics module on fixture `StatementSet`s** (primary seam). Build small adjusted sets with the shared statement fixture helpers, including the Owner Earnings and Net Assets in Use memo rows, an income-tax row, and cash-flow dividend/buyback/issuance rows. Cases: ROCE with opening/closing average; oldest period absent; average ≤ 0 → NaN; After-tax Owner Earnings uses the income-statement tax row, not the cash-flow `IncomeTaxes` rows; Distributions picks the first present concept per period (concept switch across years, no double count), treats missing components as 0, ignores minority-interest dividends; Retained Earnings arithmetic. Also the applies-by-default behaviour: specs built from empty prefs include `owner_earnings`, and applying them yields an Owner Earnings row equal to pretax + D&A + ΔNWC. Prior art: the pure tests in the adjustments engine test module and the statement fixtures module.
2. **Price router with fake provider clients.** Inject fake adapters/clients and a temporary state/cache directory. Cases: preferred provider used when it supports the ticker; fallback on unsupported ticker and on rate-limit body; local daily limit refuses before calling; counts survive a new router instance; current price served from cache within the day and refetched the next day (injected clock); historical close fetched once then always cached; both failing → unavailable with a reason; month-end selection picks the last trading day of the month. Prior art: the Finnhub and Alpha Vantage client tests (fake `_fetch_endpoint` / patched requests).
3. **`valuation_inputs` I/O through `WizardDatabaseManager` on a temp DB.** Upsert/read/update-on-conflict/delete/no-op cases, case-insensitive ticker, schema bootstrap adds the table to a DB that only has `adjustment_preferences`. Prior art: the wizard database test module.
4. **One page-level test** of the ROCE sub-page through the FastAPI test client, with `load_adjusted`, the cover-share reader and price router monkeypatched and a temp wizard DB: renders ROCE and the test result; refusal names the year when Owner Earnings is missing; "price unavailable" path; POST saves N and a price then GET reflects them; `period=quarterly` shows only the notice. Prior art: the Business Understanding page tests (monkeypatched `run_task`, `TestClient`).

Optional `data`-marked test (run by `make test`'s `-m data` step, skipped without prerequisites): for the data-test tickers, the cover-page share count is present and positive for every cached annual period, and `distributions` returns values for each period. Prior art: the engine invariants data test.

## Out of Scope

- **Future scope — alternative Retained Earnings Test:** (ΔOwner Earnings over N years × P/E at the start of the window) ÷ Σ Retained Earnings: value created at a constant multiple, removing the effect of a change in the market's multiple. Not built; the page may mention it in its intro as an alternative reading.
- Quarterly ROCE or Retained Earnings Test (annual only across the wizard).
- An unadjusted (reported-figures) ROCE.
- A computed or effective tax rate.
- Per-share figures.
- Shares outstanding, dividends or buybacks from price APIs (EDGAR only).
- Paid API tiers, more than two price providers, intraday prices, price charts.
- Correcting for stock splits between a 10-K's cover date and the price date (see Further Notes).
- Using the price router for non-US tickers.
- Reinvestment Rate and Reinvestment-implied Growth (added to the metrics module by `growth-estimation.md`).
- Neff Ratio, Distributions yield and Target Neff (`neff-ratio.md`).
- Changing how Owner Earnings or Net Assets in Use are computed (owned by `owner-earnings-exceptional-items.md` and `assets-in-use.md`).

## Further Notes

- **Known limitations.** (a) If a stock split happens after the latest 10-K's cover date, "now" market cap is wrong until the next 10-K; same for a split between a start-of-window fiscal year end and its 10-K cover date. (b) Multi-class companies whose classes trade at very different prices (e.g. Berkshire A/B) get price × total shares, which can be badly off; the investor can type a corrected price but not a share count. (c) Tax-withholding payments on employee share settlements (`PaymentsRelatedToTaxWithholdingForShareBasedCompensation`) are not counted as repurchases, though some filers label them so.
- The metrics module is the single owner of these five calculations. Growth Estimation and Neff Ratio must call it and not re-derive any of them from statement rows.

### Assumptions

1. **No saved Owner Earnings prefs:** `owner_earnings` declares that it applies by default, using the generic mechanism defined in `assets-in-use.md` (honoured by the specs builder). It then runs with empty params (every maintenance % = 0) for every ticker, so its memo rows also appear on the adjusted statement view. Metric consumers use the existing `load_adjusted(ticker, "annual")` with no `until`.
2. The metrics read Owner Earnings and Net Assets in Use (`adj_NetAssetsInUse`) from the adjustment types' memo rows, via concept constants exported by those type modules (the Owner Earnings constant replaces today's literal).
3. Income tax expense = the income statement's non-dimensional `IncomeTaxes` row, raw sign; a window year without it makes the test refuse (named), like missing Owner Earnings.
4. Distributions components are matched by ordered concept-QName lists (first present per period wins; absent = 0); minority-interest dividends and tax-withholding share settlements are excluded.
5. Window = latest N annual periods; start of window = fiscal year end of period N+1; N+1 cached annual periods required, so N ≤ cached periods − 1.
6. "Month-end close" = close on the last trading day of the calendar month containing the start-of-window fiscal year end, not split-adjusted.
7. Start-of-window shares = cover page of the 10-K for period N+1; "now" shares = cover page of the latest 10-K. Multi-class: sum of per-class facts when no undimensioned total exists.
8. Cover-page shares are added to the edgartools cache as a separate small frame per annual bundle (schema version bump), exposed by a read function, not inserted into any statement.
9. ROCE average ≤ 0 → "n/m"; Σ Retained Earnings ≤ 0 → test "n/m"; both with the reason shown.
10. ROCE table shows the latest `HISTORY_YEARS` (10) annual periods; the build-up table shows exactly the N window years.
11. `valuation_inputs` uses `(ticker, exchange, subpage, input_key)` as primary key, no surrogate id; `subpage` is a namespace that is either a sub-page slug or the shared `price` namespace. Its I/O is upsert, read, and delete-by-key.
12. Price overrides: `current` (date = `updated_at`) applies only on the day it was typed; `month_end_close:<YYYY-MM-DD>` applies forever for that date; blank input deletes the override.
13. Override resolution lives in one web-layer helper (shared with Neff Ratio); the router itself never reads the wizard DB.
14. Router call counts and its price cache are JSON files under the data directory, not wizard DB tables; the clients' own never-expiring disk cache is bypassed for price calls.
15. "Not on plan" answers mark (provider, ticker, kind) unsupported for the day; rate-limit answers mark the provider exhausted for the day.
16. Router limits and capability flags are constants in the central config module, filled from the implementer's verified-facts table.
17. `period=quarterly` renders only the shared "annual only" notice partial (no figures); that partial does not exist yet, and whichever grilled page lands first creates it.
18. Sub-page slug `roce`, title "ROCE", order 2 on Business Quality.
19. Inputs are saved through the existing one-table save form; a generic "reload after save" opt-in on the save form makes the server-computed result refresh.
20. The POST handler computes the start-of-window date from the submitted N to key a typed historical close.
21. The test's per-year inputs come from the fully adjusted set (`until=None`), not a stage snapshot.
