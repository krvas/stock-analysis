# Capitalizing Opex

The investor ticks operating-expense lines to capitalize and sets an
amortization period in years; Save stores them, and the adjusted statements
then carry a capitalized asset, an amortization expense and an equity offset.

## Sub-features

- `o2c-list` the detailed income-statement opex lines render with `Capitalize` and `Years` inputs.
- `o2c-save` ticking a line with years and saving persists it; unticking and saving deletes it.
- `o2c-downstream` the capitalized net asset appears on the adjusted balance sheet and as an asset line on Assets in Use.

## How to get to it (user POV)

- Wizard nav: Adjustments tab, then `Capitalizing Opex`.
- URL: `/wizard/AAPL/adjustments/opex-to-capex`.

## Driving it with the built-in browser

Preconditions: baseline; View is greyed (`Detailed only`).

- **Capitalize.** On the R&D row (`data-row-id` containing `ResearchAndDevelopmentExpense`), click the `capitalize` checkbox and type `5` into `years`. Click `Save`; status `Saved ✓`.
- **Persisted.** `scripts/prefs.py "$RUN" AAPL` lists `opex_to_capex` for that row id with value `5.0`. Reload: checkbox ticked, years 5.
- **Downstream.** `/wizard/AAPL/adjustments/assets-in-use` lists a capitalized R&D asset line; `/statements/AAPL/balance` on Basis `Adjusted` shows it under assets.
- **Untick.** Untick, Save; `prefs.py` no longer lists it.

## Gotchas

- Ticking without years fails the save with `years is required when capitalize is true`.
- Row ids are matched exactly; a refreshed filing can rename a line and orphan an old choice silently.
