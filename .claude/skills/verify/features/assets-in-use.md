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
(`scripts/prefs.py "$RUN" AAPL` shows none). `X` below is
`scripts/expected.py "$RUN" AAPL assets-in-use --settings '<drawer JSON>'`.

- **Targets.** Run `X`. `targets.asset` and `targets.liability` name the row
  id and unique label of the largest asset and liability; use those below.
- **Defaults.** Open the page. Run the `X --js` snippet: no mismatches across
  every row, with Gross = Net = Total assets in each period.
- **Live Gross.** Reach the target asset's `% in use` input (label ref, then
  the next `find textbox` ref), `scroll_to`, `triple_click`, type `50`, press
  `Tab`. The input reader shows only that row at `50`. Run
  `X --pct <asset id>=50 --js`: no mismatches.
- **Live Net.** Reach the target liability's `Net out` checkbox (label ref,
  then the next `find checkbox` ref), `scroll_to`, `left_click`. Run
  `X --pct <asset id>=50 --net <liability id> --rows total_assets,gross_assets_in_use,net_assets_in_use --js`:
  no mismatches; Net moved and Gross did not.
- **Save.** `find` `Save`, click, poll `.wizard-save-status` to `Saved ✓`.
  `scripts/prefs.py "$RUN" AAPL` lists the asset at `50.0`, the liability at
  `1.0` and every other asset at `100.0`.
- **Reload.** Navigate to the page again. The input reader shows the asset at
  50 and the liability ticked; `X --rows gross_assets_in_use,net_assets_in_use --js`
  (now read from the saved choices) has no mismatches.
- **Validate.** Clear the asset's input (`triple_click`, `Delete`, `Tab`) and
  Save. The status reads `<asset label>: % in use is required` with
  `data-state="error"`, and `prefs.py` output is unchanged.
- **Memo rows.** Open `/statements/AAPL/balance`, set Basis `Adjusted` in
  the drawer, Apply. Run
  `scripts/expected.py "$RUN" AAPL balance --settings '<drawer JSON>' --rows us-gaap_Assets,adj_GrossAssetsInUse,adj_NetAssetsInUse,us-gaap_LiabilitiesAndStockholdersEquity --js`:
  no mismatches. Rows `adj_GrossAssetsInUse` and `adj_NetAssetsInUse` follow
  `us-gaap_Assets` in the `statement-table-data` row order.
- **Proof.** Save each `expected.py` JSON, each snippet result and the
  `prefs.py` output to `$RUN/evidence/aiu-*.json`.

## Gotchas

- With 10 periods the `Net out` column is past the right edge; `scroll_to` the checkbox ref first.
- Labels repeat (`Marketable securities`, `Term debt`); act only on rows whose label is unique, and confirm by `data-row-id`.
- Save writes a row for every asset, including those left at 100.
- Basis is a cookie in the browser pane; set it back to `Reported` afterwards.
