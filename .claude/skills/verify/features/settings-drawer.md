# Settings drawer

A drawer opened from the gear in the page nav sets global settings (period
type, number of periods, view) and per-page settings (basis, current and
previous period, items per side); settings a page cannot honour are greyed
with a reason.

## Sub-features

- `set-open` the gear opens the drawer; Esc and × close it, and the gear reopens it after either.
- `set-apply` changing a field and pressing Apply, or Enter in a number field, reloads the page with the new setting.
- `set-save-failed` a save that fails (network or 5xx) shows `Settings were not saved: ...` in the open drawer and re-enables Apply.
- `set-instant` View applies on change without Apply.
- `set-greyed` greyed fields are disabled with a visible reason (e.g. `Two periods`).
- `set-refused` an invalid combination (previous period not older than current) shows the error and keeps the old values.

## How to get to it (user POV)

- Gear button (accessible name `Settings`) at the right of the page nav on any statements or wizard page.

## Driving it with the built-in browser

Preconditions: baseline.

- **Open.** `find` `Settings` button, click. Heading `Settings` appears with `Global` and `This page` sections.
- **Apply.** Set `#setting-num_periods` to `3` via `form_input`, click `Apply`. The table shows 3 period columns. Typing in the field and pressing Enter does the same.
- **Failed save.** Stub `window.fetch` in the page to resolve a 500, click `Apply`: `[data-drawer-error]` shows the message, the drawer stays open, `[data-drawer-apply]` is disabled only while the request runs.
- **Greyed.** On `/wizard/AAPL/business-understanding/fund-flow`, `#setting-num_periods` is disabled, `aria-describedby` points at `#setting-num_periods-reason`, which reads `Two periods`.
- **Refused.** On `/wizard/AAPL/business-understanding/fund-flow`, set current and previous period to the same offset, Apply; the drawer reopens with `Previous period must be older than the current period`.

## Gotchas

- The drawer is painted by JS from `#settings-drawer-data` (`Drawer.serialize()`); `curl` sees an empty `<dialog>`. Read field state from that JSON, or drive the browser.
- `document.getElementById('settings-drawer').open` reports open state for an Esc/close check.
- Settings are a cookie in the browser pane, shared by every page in it; restore defaults when done.
- `form_input` on a select sets the option value (`adjusted`), not the label.
