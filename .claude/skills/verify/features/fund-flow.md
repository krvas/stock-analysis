# Fund Flow

The investor compares two balance sheets side by side: each line shows the
current and previous period and the change between them, on the reported or
adjusted basis, with adjustment memo rows left out.

## Sub-features

- `ff-table` every balance-sheet line shows current, previous and `Change` = current − previous.
- `ff-periods` the drawer's `Current period` and `Previous period` pick the two columns.
- `ff-no-memo` on the adjusted basis, memo rows such as Gross and Net assets in use stay out while the `.adjustments-note` names the adjustments.
- `ff-refused` the same period for both is refused in the drawer (see [Settings drawer](./settings-drawer.md)).

## How to get to it (user POV)

- Wizard nav: Business Understanding tab, then `Fund Flow`.
- URL: `/wizard/AAPL/business-understanding/fund-flow`.

## Driving it with the built-in browser

Preconditions: baseline. `X` below is
`scripts/expected.py "$RUN" AAPL fund-flow --settings '<drawer JSON>'`.

- **Table.** Open the page. Run `X --js`: no mismatches and `unchecked` 0, so
  every row's label, both period cells and `Change`
  match the data.
- **Periods.** Open the drawer, set `Previous period` to `3 back`
  (`form_input` on the select), click `Apply`. The column headers become the
  current period, the period three back, and `Change`. Re-read the drawer
  JSON; `X --rows us-gaap_Assets,us-gaap_LiabilitiesAndStockholdersEquity --js`
  has no mismatches.
- **No memo rows.** With saved Assets in Use choices (run that recipe's Save
  first), set Basis `Adjusted`, Apply. `.adjustments-note` reads
  `Adjusted for: …`, and `X --js` has no mismatches and `unchecked` 0. The
  snippet reports any painted row whose id starts with `adj_` (such as
  `adj_GrossAssetsInUse`) as a mismatch whatever `expect` says, so the check
  holds even if the Fund Flow builder starts passing memo rows through.
- **Proof.** Save each `X` JSON and snippet result to `$RUN/evidence/ff-*.json`.

## Gotchas

- Only `Change` is computed on this page; the period cells are the balance sheet as stored, so a mismatch there points at the statement load, not Fund Flow.
- Static cells have no `data-row-id`; the snippet maps rows through `fund-flow-table-data`.
- With fewer than two distinct periods the page shows `Not enough periods` instead of a table, and `X` prints `not_enough_periods`.
- Restore `Previous period` to `1 back` and Basis to `Reported` when done.
