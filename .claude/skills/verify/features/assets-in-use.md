# Assets in Use

The investor sets a "% in use" on each balance-sheet asset line and ticks
"Net out" on liabilities; Gross and Net Assets in Use recalculate as they
type, Save stores the choices, and the adjusted balance sheet shows Gross
and Net Assets in Use as memo rows after Total assets.

## Sub-features

- `aiu-defaults` every asset at 100, every liability unticked, Gross = Net = Total assets.
- `aiu-live-gross` editing a % changes Gross (and Net) immediately.
- `aiu-live-net` ticking Net out changes Net only.
- `aiu-save` Save persists; reload shows the saved values.
- `aiu-validate` blank or out-of-range % is rejected naming the line.
- `aiu-memo-rows` adjusted balance sheet shows both memo rows; the sheet still balances.
- `aiu-annual-only` Period type is greyed with reason `Annual only`.

## How to get to it (user POV)

- Wizard nav: Adjustments tab, then the `Assets in Use` sub-tab.
- URL: `/wizard/AAPL/adjustments/assets-in-use`.
- Memo rows: `/statements/AAPL/balance` with Basis `Adjusted`; the page's
  `View balance sheet` link goes there.

## Driving it with the built-in browser

Preconditions: baseline; AAPL has no saved `assets_in_use` rows in the run DB
(`scripts/prefs.py "$RUN" AAPL` shows none).

- **Defaults.** Open the page. Read `td[data-calc-slot][data-row-id="gross_assets_in_use"]` and `...="net_assets_in_use"` for the first period; both equal the `total_assets` row (AAPL 2025-09-27: 359,241).
- **Live Gross.** `find 'type="number"'`; the asset inputs follow `Number of periods`, and PP&E is the 8th asset. `scroll_to` + `triple_click` its ref, type `50`, press `Tab`. Confirm `td[data-input-slot][data-row-id="us-gaap_PropertyPlantAndEquipmentNet"][data-col-id="pct_in_use"] input` reads 50. Gross and Net become 359,241 − 0.5 × 49,834 = 334,324.
- **Live Net.** `find` checkbox refs; the first is Accounts payable (`data-row-id="us-gaap_AccountsPayableCurrent"`, `data-col-id="net_out"`). `scroll_to` it, `left_click`. Net becomes 334,324 − 69,860 = 264,464; Gross unchanged.
- **Save.** `find` `Save`, click. `.wizard-save-status` reads `Saved ✓`. `scripts/prefs.py "$RUN" AAPL` lists PP&E `50.0` and Accounts payable `1.0` (plus every other asset at `100.0`).
- **Reload.** Navigate to the page again; PP&E shows 50, Accounts payable is ticked, Gross/Net as above.
- **Validate.** Clear a % input and Save; the status shows an error naming that line and `prefs.py` is unchanged.
- **Memo rows.** Open `/statements/AAPL/balance`, Settings → `#setting-basis` = `adjusted` → Apply. Rows `Gross assets in use` 334,324 and `Net assets in use` 264,464 sit right after `Total assets`; `Total assets` equals `Total liabilities and shareholders’ equity`.
- **Proof.** Save the before/after cell reads, `prefs.py` output and the balance-sheet rows to `$RUN/evidence/aiu-*.json`.

## Gotchas

- With 10 periods the `Net out` column is past the right edge; `scroll_to` the checkbox ref first.
- Labels repeat (`Marketable securities` ×3, `Term debt` ×2); select rows by `data-row-id`, not label.
- Save writes a row for every asset, including those left at 100.
- Basis is a cookie in the browser pane; set it back to `Reported` afterwards.
