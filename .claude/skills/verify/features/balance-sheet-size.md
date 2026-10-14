# Balance Sheet Size

Two treemaps show the largest balance-sheet items as of one period: assets on
the left, liabilities and equity on the right, each box sized by its value
and labelled with the value in billions.

## Sub-features

- `bss-treemaps` each side shows its top items, largest first, with equity as one `Equity` box on the right.
- `bss-area` each box's area is its share of the side's shown total.
- `bss-items` the drawer's `Items per side` sets how many boxes each side shows.
- `bss-as-of` the `As of` line names the drawer's `Current period`.

## How to get to it (user POV)

- Wizard nav: Business Understanding tab, then `Balance Sheet Size`.
- URL: `/wizard/AAPL/business-understanding/balance-sheet-size`.

## Driving it with the built-in browser

Preconditions: baseline. `X` below is
`scripts/expected.py "$RUN" AAPL balance-sheet-size --settings '<drawer JSON>'`.

- **Treemaps.** Open the page. Run `X --js`: no mismatches. The snippet reads
  each `[data-treemap="assets"|"liabilities"] .treemap-box` in order (label
  in `strong`, value in `span`, size from `style.width` × `style.height` in
  percent) and checks the `As of` line.
- **Items per side.** Open the drawer, `find` `Items per side` textbox,
  `triple_click`, type `3`, click `Apply`. Re-read the drawer JSON;
  `X --js` has no mismatches and each side has 3 boxes.
- **Screenshot.** Take one and describe it: two coloured treemaps, the
  largest box top-left on each side.
- **Proof.** Save each `X` JSON and snippet result to `$RUN/evidence/bss-*.json`.

## Gotchas

- The treemap is painted by `wizard/balance_sheet_size.js` from embedded JSON, so `curl` HTML has no boxes; read the DOM after `navigate`.
- Boxes carry no row id; the snippet matches by order and label. Labels can repeat (`Term debt`), so a label match alone is not proof of the row.
- Values on the page are rounded to $0.1B; compare through the snippet, not by eye.
- Restore `Items per side` to `5` when done.
