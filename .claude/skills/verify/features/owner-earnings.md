# Owner Earnings

The investor enters a maintenance % for each D&A item and for ΔNWC; the
Owner Earnings row recalculates as they type, and Save stores the
percentages, which then appear as memo rows on the adjusted cash-flow
statement.

## Sub-features

- `oe-nwc-table` the ΔNWC build-up table renders with a Change in NWC total.
- `oe-live` editing a maintenance % changes the Owner earnings row immediately.
- `oe-save` Save persists; reload shows the saved %.
- `oe-memo-rows` adjusted cash-flow statement shows Maintenance capex, Maintenance working capital and Owner earnings after CFO.

## How to get to it (user POV)

- Wizard nav: Adjustments tab, then `Owner Earnings`.
- URL: `/wizard/AAPL/adjustments/owner-earnings`.
- Memo rows: `/statements/AAPL/cashflow` with Basis `Adjusted`.

## Driving it with the built-in browser

Preconditions: baseline.

- **Live.** Read `td[data-calc-slot][data-row-id="owner_earnings"]` for the first period. Set the `nwc` row's `maintenance_pct` input to `50` (triple_click, type, Tab). Owner earnings changes by −0.5 × the ΔNWC cell of that period.
- **Save.** Click `Save`; `.wizard-save-status` reads `Saved ✓`; `scripts/prefs.py "$RUN" AAPL` lists `owner_earnings` / `maintenance_nwc` `50.0`.
- **Reload.** The `nwc` row's input shows 50.
- **Memo rows.** `/statements/AAPL/cashflow`, Basis `Adjusted`: `Owner earnings` row after operating cash flow equals the page's Owner earnings cell.

## Gotchas

- A blank maintenance % saves as 0, unlike Assets in Use, which rejects blanks.
- The page reads the stage before owner earnings, so capitalized-opex amortization rows appear as D&A items only when opex-to-capex choices exist.
