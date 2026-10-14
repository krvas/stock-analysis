# Stock Analysis verification map

The maintained source for verifying what a user sees in the web app. Read
this index, then use the matching feature file as the recipe.

## Baseline preconditions

- A server started by this run via `scripts/serve.py "$RUN" "$PORT"`, and
  `scripts/doctor.sh "$RUN"` printing no `FAIL`.
- Ticker `AAPL` (cached). `MU` is the cached ticker with no saved choices.
- Settings drawer at defaults: Period type `Annual`, Number of periods `10`,
  View `Standard`, Basis `Reported`, Current period `Latest`, Previous period
  `1 back`, Items per side `5`.

## Driving conventions

- Built-in browser tools only (`mcp__Claude_Browser__*`); `curl` for raw HTML.
- Prefer accessible names and the `data-row-id` / `data-col-id` slots over
  coordinates.
- Set values with real clicks and typing (`form_input` only for a native
  select); read them with `javascript_tool`.
- Expected numbers come from `scripts/expected.py`, never from a recipe.
- After a save, reload the page before claiming persistence.

## Proof and skip reporting

- Record the feature ID and the entry point with every artifact in
  `$RUN/evidence/`.
- Mutation proof = page state after reload + `scripts/prefs.py` output.
- Report an entry point you could not reach with the attempted action and
  the unmet precondition; never count it as verified through another path.

## Feature entry contract

Each file: an H1, one paragraph of user-visible behaviour, then exactly the
H2s `Sub-features`, `How to get to it (user POV)`, `Driving it with the
built-in browser`, `Gotchas`.

## Features

- [Assets in Use](./assets-in-use.md): % in use and Net out inputs, live Gross/Net, save, memo rows.
- [Owner Earnings](./owner-earnings.md): maintenance % inputs and the live Owner Earnings row.
- [Capitalizing Opex](./opex-to-capex.md): capitalize checkbox + years, and the capitalized asset downstream.
- [Statements pages](./statements.md): income / balance / cash-flow tables, reported vs adjusted basis and the adjustments note.
- [Fund Flow](./fund-flow.md): current vs previous balance sheet with the change per line.
- [Balance Sheet Size](./balance-sheet-size.md): asset and liability treemaps, items per side.
- [Settings drawer](./settings-drawer.md): global and per-page settings, greyed settings with reasons.
