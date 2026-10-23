# Spec: Assets in Use

- **Status:** ready for agent, not built
- **Depends on:** none. The `owner_earnings` adjustment type it runs after already exists. `owner-earnings-exceptional-items.md` changes how Owner Earnings is computed but nothing on this page.
- **Consumed by:** `roce.md` (ROCE's denominator is the average of opening and closing Net Assets in Use).
- **Related docs:** `CONTEXT.md` (Gross Assets in Use, Net Assets in Use, ROCE), `specs/vision.md` (Page 2 › "Assets in-use"), `specs/adjustments_architecture.md` (§2 pipeline and registry, §8 stage semantics), `specs/features/dimensional-breakdowns.md` (detailed-view rows, future scope), `specs/STATE.md` (stale; trust the code).

## Problem Statement

The investor wants to judge how well a business uses its capital. ROCE divides Owner Earnings by the capital the business uses to earn them. The reported balance sheet overstates that capital in two ways:

- **It includes assets that are not productive yet, or not fully productive.** A machine that has been under construction for three years earns nothing today. A theme park in its ramp-up years earns less than an established one of the same cost. Counting these at full value makes a business that is investing for growth look worse than it is.
- **It ignores free funding from operations.** Payables are money suppliers lend the business for nothing. Netting them off the assets shows the capital the owners actually have to put in. Other liabilities, such as advances from customers, may or may not deserve the same treatment, and the investor wants to decide that line by line.

Today the Assets in Use sub-page is an empty "not implemented" slot. No stored judgment exists for which assets are in use or which liabilities to net, so ROCE has no denominator.

## Solution

An **Assets in Use** sub-page on the Adjustments page. It lists the balance sheet's line items, after earlier adjustments such as capitalized opex, for the latest five annual periods:

- Each **asset line** has an editable **"% in use"**, default 100%. One value per line applies to every period.
- Each **liability line** has a **"Net out"** checkbox, default unticked.
- Two live-calculated rows update as the investor types: **Gross Assets in Use** and **Net Assets in Use**.

Saving stores these choices as adjustment preferences. A new adjustment type, `assets_in_use`, runs last in the pipeline. It inserts two memo rows into the adjusted balance sheet for every cached period: Gross Assets in Use and Net Assets in Use. Memo rows are shown but never summed into any total. These rows show up on the adjusted statements view, and ROCE reads Net Assets in Use from them.

With no choices saved, Gross Assets in Use = Net Assets in Use = reported total assets. The rows exist even if the investor never opens the page.

## User Stories

1. As the investor, I want an Assets in Use sub-page under Adjustments, so that I can judge the capital the business actually uses before computing ROCE.
2. As the investor, I want the page to show the balance sheet after earlier adjustments, so that I can set a % in use on assets those adjustments created (such as a capitalized-advertising net asset).
3. As the investor, I want to see every asset line item at the same level as Balance Sheet Size (summary-view lines with no calc children), so that each line is counted once and the lines add up to total assets.
4. As the investor, I want subtotals such as "Total current assets" left out of the editable list, so that I cannot count the same asset twice.
5. As the investor, I want the latest five annual periods shown side by side, so that I can see how each line has grown before deciding how much of it is productive.
6. As the investor, I want a "% in use" input on each asset line, so that I can exclude construction in progress or discount an asset still ramping up.
7. As the investor, I want "% in use" to default to 100%, so that I only have to touch the lines I disagree with.
8. As the investor, I want one "% in use" per line that applies to all periods, so that I make one judgment per asset without filling in a grid.
9. As the investor, I want "% in use" limited to 0–100, so that I cannot enter a value that makes no sense.
10. As the investor, I want a clear error naming the line when I leave a "% in use" blank or out of range, so that I can fix it before my choices are saved.
11. As the investor, I want to see every liability line item, so that I can decide line by line which ones to net out.
12. As the investor, I want a "Net out" checkbox on each liability line, so that I can net payables but not, say, advances from customers or debt.
13. As the investor, I want nothing netted by default, so that Net Assets in Use equals Gross Assets in Use until I choose otherwise.
14. As the investor, I want equity lines left out of the liability list, so that I cannot "net out" the owners' own capital.
15. As the investor, I want a Total assets row at the top, so that I can see what Gross Assets in Use is being compared with.
16. As the investor, I want a Gross Assets in Use row that recalculates as I type, so that I can see the effect of each % right away.
17. As the investor, I want a Net Assets in Use row that recalculates as I tick or untick liabilities, so that I can see the denominator ROCE will use.
18. As the investor, I want a Save button that stores my choices and reports success or failure inline, so that I know they persisted.
19. As the investor, I want my saved % and checkboxes pre-filled when I come back, so that I can review and refine earlier judgments.
20. As the investor, I want unticking a liability and saving to remove the stored netting, so that the stored state always matches what I see.
21. As the investor, I want my choices saved as rules (a % per line, a flag per liability), not as restated numbers, so that they re-apply when a newer 10-K refreshes the data.
22. As the investor, I want the adjusted balance sheet to show Gross Assets in Use and Net Assets in Use as memo rows, so that I can see them next to the reported figures on the statements page.
23. As the investor, I want those memo rows to leave every reported total unchanged, so that the balance sheet still balances.
24. As the investor, I want Gross and Net Assets in Use computed for every cached annual period, not just the five shown, so that ROCE can average opening and closing balances across its whole history.
25. As the investor, I want Net Assets in Use to exist even if I never open this page, so that ROCE works with sensible defaults (everything in use, nothing netted).
26. As the investor, I want a line that is a leaf in one year but a subtotal in another to be handled without double counting, so that a filer restructuring its balance sheet doesn't distort the result.
27. As the investor, I want a contra-asset line (for example an allowance shown as its own leaf) to reduce Gross Assets in Use, so that the result matches how the line enters total assets.
28. As the investor, I want an "annual only" notice when I open the page with the quarterly period, so that I'm not shown misleading partial-year data.
29. As the investor, I want the page to explain in plain words what "in use" and "net out" mean, with the construction and theme-park examples, so that I apply the idea the same way across companies.
30. As the investor, I want a link from the page to the adjusted statements, so that I can check where the memo rows landed.
31. As the investor, I want stored preferences for lines that no longer exist in refreshed filings to be ignored quietly, so that a renamed line doesn't break the page or the pipeline.
32. As the investor, I want the Assets in Use adjustment listed with the other saved adjustments in a short description (how many assets have a % set, how many liabilities are netted), so that I can tell at a glance what I changed.

## Implementation Decisions

### Shared balance-sheet leaf definition

- Balance Sheet Size already defines an "item": a summary-view balance-sheet row with no calc children in that period's calc tree. Each item belongs to one side, found by walking the calc-parent chain to its root (total assets, or total liabilities and equity). Rows whose chain passes an equity parent are equity.
- This definition moves out of the Balance Sheet Size builder (where it is private today) into one public, pure helper beside the statement model. Both Balance Sheet Size and `assets_in_use` call it. For one period it returns each leaf's row id, label, side, equity flag and **effective weight**. The effective weight is the product of the calc weights along the chain to the root in that period.
- Balance Sheet Size keeps its own presentation rules on top of the helper: display-sign values, dropping non-positive leaves, netting equity into one item, top ten. Its behaviour does not change.

### Quantities (per period p, raw signs)

- **Contribution** of leaf i: `c_i,p = e_i,p × v_i,p`. Here e is the effective weight and v is the raw value. With zero residuals, the contributions of all asset leaves sum to total assets. Liability leaves likewise sum to total liabilities and equity, less equity.
- **Asset leaves A_p**: leaves whose root is total assets.
- **Liability leaves L_p**: leaves whose root is total liabilities and equity and whose chain does not pass an equity parent.
- `u_i` = saved % in use of row i (default 100). `n_j` = 1 if liability row j is saved as netted, else 0.
- **Gross Assets in Use**: `Gross_p = TotalAssets_p − Σ_{i∈A_p} c_i,p × (1 − u_i/100)`. This equals `Σ c_i,p × u_i/100` when the calc residual is zero, which is the expected case on real filings. Writing it as "total assets minus the not-in-use part" makes the defaults reproduce reported total assets exactly, even when a residual exists.
- **Net Assets in Use**: `Net_p = Gross_p − Σ_{j∈L_p} c_j,p × n_j`.
- A row's % applies only in periods where that row is a leaf. In a period where it has calc children, its children count at their own %.
- If total assets is missing for a period, no memo values are produced for that period.

### New adjustment type `assets_in_use` (pure, in the adjustments package)

- Implements the type interface: `from_prefs`, `apply`, `describe`.
- **Params:** one mapping `row_id → value` taken from `adjustment_preferences` rows of this type. `apply` classifies each key against the balance sheet it receives:
  - a key matching an asset leaf is a % in use;
  - a key matching a liability leaf with value 1.0 is netted;
  - any other key is ignored. This covers rows that vanished in refreshed filings.
- **apply** computes Gross and Net for every period of the balance sheet it receives. It returns two `NewRow`s on the balance sheet with no calc parent, so they are memo rows the engine never sums:
  - `adj_GrossAssetsInUse`, label "Gross assets in use";
  - `adj_NetAssetsInUse`, label "Net assets in use".
  - Both are placed right after the total assets row, Gross first. The type module exports the two concept names as constants, so consumers (ROCE) can find the rows.
- **describe:** "Assets in use: % set on k asset line(s), m liability line(s) netted". Here k counts asset keys whose value is not 100.
- **Pipeline:** registered in the adjustment registry and appended last to the pipeline order, after `owner_earnings`.
- **Always applied:** the defaults are meaningful and ROCE always needs Net Assets in Use, so the type is applied even when no preferences of its type are saved. This is done generically, not as an `assets_in_use` special case:
  - a type module may declare that it applies by default;
  - the specs builder (saved preferences → specs) emits an empty-params spec for every such type that has no saved rows, including when the preferences table is empty.

### Persistence

- Uses the existing `adjustment_preferences` table through `WizardDatabaseManager`. No schema change.
- Each row stores `adjustment_type = 'assets_in_use'`, `base_concept = row_id` (verbatim from `get_row_id`), and `statement = base_concept_statement = 'BS'`.
- Asset row: `value` = % in use (0–100). Liability row: `value = 1.0` means netted; no row means not netted.
- The wizard schema's column comment on `value` is updated to describe both meanings.

### Sub-page (context builder, POST handler, template)

- **Registry:** the existing `assets-in-use` sub-page entry gains a context builder and a POST handler. This is identity only.
- **Page module:** a new subpage-specific page module holds all page code:
  - the context builder;
  - the POST handler;
  - one public function that returns the page's asset and liability rows for the displayed periods. The builder and the handler both call it, so they always agree on which posted ids are assets and which are liabilities.
- **Stage:** both use `load_for_basis(ticker, "annual", "adjusted", until="assets_in_use")`, which is the input to this type: capitalized-opex rows are present, the memo rows are not.
- **Displayed periods:** the latest five annual periods.
- **Rows:** the union of leaves across those periods that have a value in at least one of them. Period cells hold contributions on the total-assets sign. They are blank where the row is not a leaf in that period.
- **One `Table`, one form, one save.** Rows in order:
  1. "Total assets" (static, level 0);
  2. asset leaves (level 1);
  3. "Gross assets in use" (calculated);
  4. liability leaves (level 1);
  5. "Net assets in use" (calculated).
- **Columns:**
  - the five period columns (static, financial);
  - `pct_in_use` (input, number), shown as "% in use";
  - `net_out` (input, boolean), shown as "Net out".
- `no_input_cells` suppresses the input that doesn't apply to a row: `net_out` on asset rows, `pct_in_use` on liability rows, both on the three structural rows.
- The structural rows use fixed lowercase ids (`total_assets`, `gross_assets_in_use`, `net_assets_in_use`), as the Owner Earnings page does with `pretax`. These cannot collide with `get_row_id` ids, which always carry a namespace prefix.
- **Live calculation:** calculated cells that use only the existing `add`/`mul`/`const`/`cell` expression nodes.
  - Gross_p = `total_assets,p + Σ_i [0.01 × pct_i × c_i,p − c_i,p]`.
  - Net_p repeats the Gross terms and adds `Σ_j (−1 × net_out_j × c_j,p)`. It must repeat them because calculated cells read model cells only, never other calculated cells.
  - Booleans coerce to 1/0 in the evaluator, and a blank cell counts as 0.
  - On saved data, the live formula matches the type's formula exactly.
- **Prefill:** each asset row gets its saved % or 100. Each liability row gets `true` if it is saved as netted, else `false`. Values are written through the `Table` write helpers before serializing.
- **POST** receives the standard `TableModel.serialize()` body. For each posted row id:
  - **asset row:** `pct_in_use` is required, numeric, 0–100. Otherwise raise `ValueError` naming the line. Upsert the %.
  - **liability row:** `net_out` true upserts 1.0; false deletes any stored row for that key.
  - **any other id** (the structural rows) is skipped.
  - A missing `rows` raises `ValueError`.
  - Returns `{ok, rows_written, rows_deleted}`, as opex-to-capex does.
- **Quarterly:** with `period=quarterly` the builder returns only an annual-only marker, and the template shows an "annual only" notice instead of the table.
- **Template:** extends the sub-page base. It contains:
  - an intro that states the principle (count only assets that are productive today) with the user's two examples (a machine under construction for three years; a theme park ramping up), and explains netting (payables are free supplier funding; advances from customers may not be);
  - the formulas for Gross and Net Assets in Use;
  - the table inside the standard wizard save form;
  - a link to the adjusted statements.
- **No changes** to the shared frontend components or the shared `Table` model. Everything above uses existing generic features.

## Testing Decisions

A good test exercises external behaviour only:

- what memo rows the engine produces for a given balance sheet and saved preferences;
- what Table payload the builder returns;
- what the POST handler writes or deletes.

Tests do not inspect private helpers or intermediate frames.

### Proposed seams (pending user confirmation)

1. **The engine with the new type, on fixture StatementSets** (prior art: `tests/test_adjustments_engine.py`, `tests/statement_fixtures.py`). Build a small balance sheet with:
   - current-asset leaves under a current-assets subtotal;
   - a construction-in-progress leaf;
   - a contra-asset leaf (weight −1);
   - payables, customer advances and debt;
   - equity rows;
   - a row that is a leaf in one period and a subtotal in another.

   Then call `apply_adjustments` and assert:
   - with no specs from preferences, the always-applied type yields Gross = Net = total assets in every period;
   - % in use reduces Gross by the expected amount, including the contra-asset sign;
   - netting reduces Net only, and only by the ticked liabilities;
   - equity keys and unknown keys have no effect;
   - a capitalized-opex net asset inserted by `opex_to_capex` earlier in the same run is counted as an asset leaf;
   - every reported total is unchanged and the memo rows have no calc parent;
   - `until="assets_in_use"` produces no memo rows;
   - `from_prefs` plus the specs builder emit the default spec when no rows of the type exist.
2. **The context builder and POST handler, with the stage loader and wizard DB monkeypatched** (prior art: `tests/test_balance_sheet_size.py`, `tests/test_adjustments_post.py`). Assert:
   - the builder's rows, columns, no-input cells, prefill (100 / saved % / saved netting) and calculated-cell expressions;
   - the quarterly marker;
   - the POST handler upserts asset %s, upserts or deletes liability netting, skips structural rows, and raises on a blank or out-of-range %.

### Regression

The existing Balance Sheet Size tests must stay green unchanged after the leaf helper is extracted. They are the regression check for the shared definition.

### Optional

A `@pytest.mark.data` extension of the engine-invariants test: on the data-test tickers, with default prefs, Gross = Net = reported total assets and the balance sheet still balances.

## Out of Scope

- **Per-period % in use** (modelling a ramp-up year by year). One value per line applies to all periods. Future scope.
- **Detailed-view (dimensional) rows.** Construction in progress is often reported below summary level. Which dimensional rows really break down their parent is an open question recorded in `specs/features/dimensional-breakdowns.md`. Future scope; this spec uses summary-view leaves only.
- **Quarterly periods.** The page is annual only. Quarterly is future scope across all five pages.
- ROCE itself, the Retained Earnings Test, `valuation_inputs` and the price router (all in `roce.md`).
- Any change to Balance Sheet Size beyond moving the leaf definition into a shared helper.
- Netting or excluding equity lines.
- AI suggestions for % in use or for which liabilities to net.
- A "preview unsaved edits" endpoint. The live calculated cells cover the preview on this page.
- Changes to the shared frontend table components or the `Table` contract.

## Further Notes

### Assumptions

- **A1.** Gross Assets in Use is computed as `TotalAssets − Σ c_i × (1 − u_i/100)` rather than a bare `Σ c_i × u_i/100`. Both are equal when the calc residual is zero, which is expected on real filings. The chosen form makes the defaults reproduce reported total assets exactly and treats any residual as 100% in use.
- **A2.** Leaf values enter as contributions (effective calc weight × raw value), so contra-asset leaves reduce the totals. The page shows these contributions, on the total-assets sign.
- **A3.** Equity leaves (chain passes an equity parent) are excluded from the liability list. This includes the equity offset that opex-to-capex inserts.
- **A4.** The leaf definition is extracted from the Balance Sheet Size builder into one shared pure helper, with no change to Balance Sheet Size's behaviour. This follows CLAUDE.md's "use the existing owner" rule and avoids keeping two copies.
- **A5.** The type is always applied through a generic "applies by default" declaration that the specs builder honours. Without it, Net Assets in Use would be missing for anyone who never saves this page, and ROCE would have no denominator.
- **A6.** Asset and liability preferences share one params mapping. `apply` and the POST handler classify keys by looking them up in the staged balance sheet; unknown keys are ignored.
- **A7.** The page shows the latest five annual periods, matching Owner Earnings. The type computes the memo rows for every cached period. Lines that are leaves only in older periods have no input and use the 100% default.
- **A8.** The page uses one table, one form and one save. Structural rows use fixed ids, and inputs that don't apply are suppressed with `no_input_cells`.
- **A9.** A blank % in use is rejected on save with an error naming the line. It is not silently treated as 0 or 100.
- **A10.** Every posted asset row is upserted, including rows left at 100. Unticked liabilities are deleted, as in opex-to-capex.
- **A11.** Both memo rows go right after the total assets row, Gross first.
- **A12.** The annual-only notice is a generic wizard template partial driven by a generic context flag, so sibling pages can reuse it. The `assets_in_use` type itself does not depend on the period type: it applies to whatever balance sheet it receives.
- **A13.** The POST handler loads the same staged annual balance sheet as the builder in order to classify posted ids. It never re-derives row ids; it only compares posted ids against `get_row_id` ids in the staged frame.
