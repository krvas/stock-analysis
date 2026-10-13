# Settings drawer

A drawer opened from the gear in the page nav sets global settings (period
type, number of periods, view) and per-page settings (basis, current and
previous period, items per side); settings a page cannot honour are greyed
with a reason.

## Sub-features

- `set-open` the gear opens the drawer.
- `set-apply` changing a field and pressing Apply reloads the page with the new setting.
- `set-instant` View applies on change without Apply.
- `set-greyed` greyed fields are disabled with a visible reason (e.g. `Annual only`).
- `set-refused` an invalid combination (previous period not older than current) shows the error and keeps the old values.

## How to get to it (user POV)

- Gear button (accessible name `Settings`) at the right of the page nav on any statements or wizard page.

## Driving it with the built-in browser

Preconditions: baseline.

- **Open.** `find` `Settings` button, click. Heading `Settings` appears with `Global` and `This page` sections.
- **Apply.** Set `#setting-num_periods` to `3` via `form_input`, click `Apply`. The table shows 3 period columns.
- **Greyed.** On `/wizard/AAPL/adjustments/assets-in-use`, `#setting-period` is disabled and `#setting-period-reason` reads `Annual only`.
- **Refused.** On `/wizard/AAPL/business-understanding/fund-flow`, set current and previous period to the same offset, Apply; the drawer reopens with `Previous period must be older than the current period`.

## Gotchas

- Settings are a cookie in the browser pane, shared by every page in it; restore defaults when done.
- `form_input` on a select sets the option value (`adjusted`), not the label.
