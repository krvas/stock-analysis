# Spec: Owner Earnings excludes exceptional items

- **Status:** ready for agent, not built
- **Depends on:** none. Prerequisite to `assets-in-use.md` (pipeline order only), `roce.md`, `growth-estimation.md` and `neff-ratio.md`, which all consume Owner Earnings.
- **Related docs:** `CONTEXT.md` (Owner Earnings), `specs/adjustments_architecture.md` (§1 verified-facts format, §2 type contract, §8 stage semantics), `specs/vision.md` (Owner's Earnings Calculations: "pre-tax, pre-exceptional item Net profit")

## Problem Statement

The glossary defines Owner Earnings as the cash a business could pay its owners each year, before tax and *excluding exceptional items*. The Owner Earnings page and the `owner_earnings` adjustment start from reported pre-tax income, which still includes one-off charges and gains: restructuring, impairments, gains on asset sales, legal settlements and so on. One bad year (a big write-down) or one lucky year (a disposal gain) distorts Owner Earnings. Every later number built on it inherits the distortion: ROCE, Retained Earnings, Reinvestment-implied Growth, the Neff Ratio. The investor cannot see which items are inflating or depressing the figure, and cannot trust the trend.

## Solution

Owner Earnings starts from pre-tax income with exceptional items removed. Fixed, deterministic rules pick the exceptional items from the income statement. There is no AI and no ticking by the investor. The rules come from research into how stockanalysis.com and Seeking Alpha compute pre-tax income "excluding unusual items", and the research findings are recorded. The Owner Earnings page shows the rows the rules removed, read-only, with each row's effect on pre-tax income per year, so the investor can see what was taken out. The maintenance % inputs work as they do today: one value per item for all years, and an unset % counts as 0.

## User Stories

1. As the investor, I want Owner Earnings to exclude exceptional items, so that one-off charges and gains do not distort my view of the recurring cash the business produces.
2. As the investor, I want exceptional items detected automatically, so that I do not have to comb through every income-statement line myself.
3. As the investor, I want detection to be rule-based and deterministic, so that the same filing always gives the same Owner Earnings.
4. As the investor, I want the rules to follow how established data providers (stockanalysis.com, Seeking Alpha) define "unusual items", so that my numbers line up with figures I can cross-check.
5. As the investor, I want the research behind the rules recorded with evidence, so that I can audit why each kind of item counts as exceptional.
6. As the investor, I want to see every row the rules removed on the Owner Earnings page, so that I know exactly what was excluded.
7. As the investor, I want each removed row shown with its label as the company reported it, so that I can find it in the 10-K.
8. As the investor, I want each removed row's effect on pre-tax income shown per year, signed, so that I can tell charges (added back) from gains (taken away).
9. As the investor, I want a total of the excluded items per year, so that I can see the overall size of the exclusion.
10. As the investor, I want the excluded rows to be read-only, so that it is clear the rules decided this, not me.
11. As the investor, I want the Owner Earnings table to show pre-tax income, then a line removing exceptional items, then D&A, ΔNWC and the maintenance deductions, so that the calculation reads top to bottom.
12. As the investor, I want the formula on the page to mention the exclusion, so that the page explains what it computes.
13. As the investor, I want the live Owner Earnings row on the page to match the Owner Earnings memo row in the adjusted cash-flow statement, so that the page and the statements never disagree.
14. As the investor, I want my existing maintenance % inputs to keep working unchanged, so that adding the exclusion costs me no re-entry.
15. As the investor, I want an unset maintenance % to keep counting as 0, so that behaviour is the same as before.
16. As the investor, I want one maintenance % per item applied to every year, as today, so that the inputs stay simple.
17. As the investor, I want saving the page to ignore the read-only rows, so that saving never writes junk preferences.
18. As the investor, I want a company with no exceptional items to show an empty excluded-items section and unchanged Owner Earnings, so that nothing is invented.
19. As the investor, I want an exceptional item and its sub-items never counted twice, so that the exclusion is not overstated.
20. As the investor, I want dimensional breakdown rows (segments, geographies) ignored by the rules, so that the same amount is not removed once per breakdown.
21. As the investor, I want the exclusion computed per year on that year's own figures, so that a charge in one year does not leak into another.
22. As the investor, I want an exceptional item that does not feed pre-tax income in a year's calculation tree to be left alone in that year, so that the rules never remove something whose sign they cannot work out.
23. As the investor, I want an expense I already capitalized on the Capitalizing Opex page (e.g. restructuring) not to be removed again, so that the two adjustments do not double count.
24. As the investor, I want a charge that is already in my D&A items not to be removed again as an exceptional item, so that it is not added back twice.
25. As the investor, I want the exclusion to run on the stage input to Owner Earnings (after Capitalizing Opex), so that it sees the same numbers as the rest of the page.
26. As the investor, I want ROCE, Retained Earnings, Growth Estimation and the Neff Ratio to use Owner Earnings that already excludes exceptional items, so that every later page shares one definition.
27. As the investor, I want reported pre-tax income on the statements page left untouched, so that the reported basis still matches the filing.
28. As the investor, I want the excluded-items section to show the same years as the Owner Earnings table, so that the two line up column for column.
29. As the investor, I want a short note above the excluded-items table explaining that the rows were chosen by fixed rules and how signs work, so that I read the numbers correctly.
30. As the investor, I want the description of the Owner Earnings adjustment (where adjustments are listed) to stay accurate, so that summaries do not mislead me.

## Implementation Decisions

### Step 1: research (done first by the implementing worker, before any rule is coded)

- The worker spawns a research task: how stockanalysis.com and Seeking Alpha compute pre-tax income "excluding unusual items" (also called "EBT excluding unusual items"), and which line items or XBRL concepts they count as unusual.
- The research must produce two things, appended to this spec file under a new "Verified facts" section:
  1. **Rule list.** One entry per category of exceptional item (for example restructuring, goodwill and asset impairment, gain or loss on sale of assets or investments, merger and acquisition costs, legal settlements; the research decides the real list). Each entry records: the category name; which source(s) treat it as unusual; the matching `us-gaap` concept QNames and/or edgartools `standard_concept` values; and how many of the data-test tickers' cached annual income statements contain a match.
  2. **Verified-facts record.** A table with columns Fact | Evidence, in the format of the table in `specs/adjustments_architecture.md` §1. Evidence is a source URL with access date, or a check against the cached bundles (ticker, period, concept). It must also record where the two sources disagree, and whether each concept appears as a non-dimensional row on cached income statements.
- Only categories both sources treat as unusual become rules (see Assumptions). Disagreements are listed for the investor, not coded.

### Rules: shape and home

- A rule matches one non-dimensional, non-abstract income-statement row by exact `standard_concept` value, exact concept QName, or concept local-name prefix (the same three matching kinds the codebase already uses, e.g. the NWC prefix). Labels are never matched. Filer-specific extension concepts are not matched.
- edgartools term names used by the rules (standard concept values, QNames, prefixes) go into the edgartools standard-terms module, which exists to hold term names used by domain code. The matching logic goes in the `owner_earnings` adjustment type module. Nothing goes into a shared/generic file (registry, Table model, generic JS).
- No new adjustment type and no registry change. The pipeline order stays opex_to_capex → owner_earnings (assets_in_use is appended later by `assets-in-use.md`).

### Detection (pure function in the `owner_earnings` type)

- New pure function `exceptional_items(income statement) -> frame` with columns `row_id, label` plus one column per period. Each period value is the row's **effect on pre-tax income**, which can be positive or negative.
- Effect, per period p: `effect_p(row) = value_p(row) × Π weights_p` along the calc path from the row up to the pre-tax income row, in period p's own calc tree. Values are raw signs. A restructuring charge of 50 that is subtracted on the way to pre-tax income has effect −50. A disposal gain of 20 that is added has effect +20.
- The pre-tax income row is the first non-dimensional row whose `standard_concept` is the pre-tax income term (same lookup as today).
- A matched row that is not a calc descendant of pre-tax income in period p gets no value for p (it is left alone that year).
- **Topmost-match only:** if a matched row has a matched calc ancestor in period p, only the ancestor counts for p.
- **No D&A double count:** a row whose concept matches a D&A item from the cash-flow statement (the existing D&A item list, including `da`-tagged adjustment rows) is skipped.
- Rows with no value in any period are dropped. Rows keep the input order of the income statement.
- The function reads the stage it is given. Because the type runs after opex_to_capex, an expense the investor capitalized is already overridden to 0 there, so its effect is 0 and nothing is double counted.

### Owner Earnings formula

- `components(ss)` gains a column `exceptional` per period: `E_p = Σ effect_p` over the exceptional items (0 when there are none).
- New formula:
  `Owner Earnings = (pretax − E) + Σ D&A_i + ΔNWC − Σ pct_i·D&A_i − pct_nwc·ΔNWC`
- `owner_earnings(parts, maintenance, nwc_pct)` applies it. `apply` keeps inserting exactly the same three cash-flow memo rows (Maintenance capex, Maintenance working capital, Owner earnings) with the same concepts, order and placement under CFO. Only the Owner earnings values change.
- Reported and adjusted pre-tax income rows are not modified. The exclusion lives only inside the Owner Earnings calculation.
- The `describe` output and the module docstring are updated to say that Owner Earnings excludes exceptional items.
- Maintenance % semantics are unchanged: one value per D&A item row id plus one for ΔNWC, all years, unset = 0, stored in `adjustment_preferences` with `adjustment_type = 'owner_earnings'`. No schema change.

### Owner Earnings page (subpage context builder, POST handler, template)

- The context builder keeps using the stage before owner earnings (`until=owner_earnings`), the same five most recent periods, and the existing two tables.
- New read-only table **"Exceptional items excluded"**: one row per exceptional item (company label, effect per period, static columns, no inputs), plus a total row. It uses the same periods as the Owner Earnings table. When there are no items, the template shows a one-line "No exceptional items found by the rules" message instead of the table.
- Owner Earnings table: insert a row "Less: exceptional items" directly after the pre-tax income row. Its static values are `−E_p`. It has no maintenance % input. The calculated Owner Earnings cell expression adds this row, so the live value equals the engine's formula. That expression stays in the subpage builder, where subpage-specific code belongs.
- POST handler: the new row id is skipped, like the pre-tax and Owner Earnings rows, so saving never writes a preference for it. The exceptional-items table is not inside the form and is never posted.
- Template: the formula line becomes "Owner earnings = Pretax income − exceptional items + D&A + ΔNWC − maintenance D&A − maintenance ΔNWC". Add a short note above the new table: the rows were picked by fixed rules, and the sign is the effect on pre-tax income (negative = charge, added back; positive = gain, removed).
- All new table payloads go through the existing Table contract and `serialize()`. Row ids are statement row ids from `get_row_id` for item rows and fixed ids for the summary rows, following the existing builder. No JS changes. The existing generic table wiring renders static and calculated cells.

### Downstream contract

- Other specs read Owner Earnings from the `owner_earnings` stage output (the Owner earnings memo row or `components` / `owner_earnings`). After this spec, that value already excludes exceptional items. No other module recomputes the exclusion.

## Testing Decisions

### What makes a good test

Test external behaviour only. Given a StatementSet and a spec, what Owner Earnings comes out? Given a stage, what does the page show? Do not assert on private helpers, intermediate frames or calc-path internals. Build small hand-made StatementSets with known numbers so each expected value can be worked out by hand in a comment, like the existing formula test.

### Proposed seams (pending user confirmation)

1. **Primary (one seam covers the feature): the adjustment engine on a fixture StatementSet.** Call `apply_adjustments(base, [AdjustmentSpec("owner_earnings", {...})])` on a hand-built StatementSet: an income statement with a pre-tax income row, an operating subtotal, and matched exceptional rows (a charge with a subtracting calc weight, a gain with an adding weight, a parent and child that both match, a dimensional breakdown of a matched concept, a matched row outside the pre-tax subtree), plus a cash-flow statement with CFO, D&A and an NWC row. Assert on the "Owner earnings" memo row values per period. Cases:
   - Charges are added back and gains removed (sign via calc weights).
   - Parent and child that both match count once.
   - Dimensional rows are ignored.
   - A row outside the pre-tax subtree is left alone.
   - No exceptional rows gives the old formula's result.
   - With an `opex_to_capex` spec that capitalizes the restructuring row, the restructuring charge is not removed a second time.
   - Maintenance % behaviour is unchanged (an unset % counts as 0).
   - Reported pre-tax income in the adjusted set is unchanged.
2. **Secondary (only if the user wants the read-only display covered): the Owner Earnings context builder** with `load_adjusted` monkeypatched to return the fixture StatementSet. Assert that the serialized "Exceptional items excluded" table lists the expected labels and signed effects, that the Owner Earnings table has the "Less: exceptional items" row with no input cell, and that a POST body containing that row id writes no preference for it.

### Prior art

- `tests/test_adjustments_engine.py`: `test_owner_earnings_formula_with_per_item_maintenance` (hand-worked expected values) and `apply_adjustments` usage.
- `tests/statement_fixtures.py`: `_row`, `make_statement`, `derived_calc_edges`, period constants. Build income and cash-flow statements separately with `make_statement` rather than `make_statement_set`, which reuses one frame for all three statements.
- `tests/test_balance_sheet_size.py`: a context builder tested by monkeypatching the staged StatementSet.
- `tests/test_adjustments_post.py`: POST handler body validation.
- Optional data test (`@pytest.mark.data`, like `test_capitalized_opex_moves_every_period_by_its_schedule`): for every data-test ticker, Owner Earnings minus the old formula equals −E per period.

## Out of Scope

- AI or human selection of exceptional items (no ticking, no overrides, no "not exceptional" toggle).
- Matching on labels or filer-specific extension concepts.
- Removing exceptional items from reported or adjusted pre-tax income, net income or any statement row other than the Owner Earnings memo rows.
- Tax effects on exceptional items. Owner Earnings stays pre-tax. After-tax Owner Earnings (defined in `roce.md`) subtracts reported income tax expense as is.
- Per-period maintenance % (one value per item for all years stays).
- Quarterly-specific handling (the cross-cutting annual-only notice belongs to the five new pages owned by the sibling specs).
- The shared metrics module (After-tax Owner Earnings, Distributions, Retained Earnings, ROCE, Reinvestment Rate). It is first defined by `roce.md`. This spec adds nothing to it.
- Any new table in the wizard DB, including `valuation_inputs` (owned by `roce.md`).
- Showing the excluded items in the statements page or adding a new memo row for them.

## Further Notes

- The categories providers usually call unusual (restructuring, impairments, asset-sale gains and losses, M&A costs, legal settlements) are mostly non-cash or one-off. Excluding an impairment from pre-tax income has the side effect of adding it back, which is consistent with Owner Earnings as a cash measure. That is why the D&A-overlap guard matters.
- Today the `owner_earnings` adjustment only runs when the ticker has at least one saved `owner_earnings` preference (specs are built from saved prefs). This spec does not change that. roce.md resolves it: `owner_earnings` adopts the generic "applies by default" declaration defined in assets-in-use.md, so it runs with empty params (every maintenance % = 0) for every ticker.

### Assumptions

1. When the two sources disagree on a category, it is **not** coded as a rule (intersection, the conservative choice). The disagreement is recorded in the verified-facts section for the investor to veto.
2. Rule kinds are limited to exact `standard_concept`, exact concept QName, and local-name prefix. No label matching and no extension concepts.
3. The research findings (rule list and verified-facts table) are appended to this spec file rather than written to a separate document.
4. The sign of an item comes from the product of calc weights along its path to pre-tax income in that period's calc tree. If the row is not under pre-tax income that year, it is skipped that year rather than guessed from its debit/credit balance.
5. Only the topmost matched row on a calc path counts.
6. A matched row whose concept is also a D&A item is skipped.
7. No new memo row is added to the cash-flow statement. The three existing memo rows stay, and only the Owner earnings values change.
8. The exceptional-items table is shown as its own read-only table, and the Owner Earnings table gets one "Less: exceptional items" row (value −E) that feeds the live calculated cell.
9. The Owner Earnings page keeps its current period behaviour. The annual-only notice is applied by the sibling specs' new pages, not added here.
10. No registry or pipeline-order change. Detection lives inside the `owner_earnings` type, not a new adjustment type.
