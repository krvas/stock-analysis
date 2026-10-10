# Statements pages

Per-ticker income statement, balance sheet and cash-flow statement tables,
on the reported figures or with saved adjustments applied, with a note
listing which adjustments are in effect.

## Sub-features

- `st-tabs` Income, Balance and Cash Flow tabs each render a table.
- `st-basis` Basis `Adjusted` shows adjusted values and adjustment rows; `Reported` shows none.
- `st-note` on the adjusted basis `.adjustments-note` reads `Adjusted for: …`, or `Adjusted basis (no adjustments applied)` when nothing the user chose is in effect.
- `st-balances` Total assets equals Total liabilities and equity on both bases.

## How to get to it (user POV)

- Top nav `Statements`, then a tab; URL `/statements/AAPL/{income|balance|cashflow}`.

## Driving it with the built-in browser

Preconditions: baseline.

- **Reported.** Open `/statements/AAPL/balance`. No `Gross assets in use` row; no `.adjustments-note`.
- **Adjusted.** Settings → `#setting-basis` = `adjusted` → Apply. The page reloads with `.adjustments-note` present and memo rows such as `Gross assets in use` after `Total assets`.
- **Note with nothing chosen.** `/statements/MU/balance` on Adjusted: note reads `Adjusted basis (no adjustments applied)` while the memo rows still show.
- **Balances.** Read the `Total assets` and `Total liabilities and shareholders’ equity` rows; first-period values are equal.

## Gotchas

- The table is painted by JS after load; read cells after `navigate` returns, not from `curl` HTML.
- Basis persists in the pane's cookie across pages; reset it to `Reported`.
