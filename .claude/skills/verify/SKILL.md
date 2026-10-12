---
name: verify
description: Launch and drive the Stock Analysis web app (FastAPI + Jinja, statements pages and the per-ticker analysis wizard) in the built-in browser to prove a change works the way a user sees it. Use after changing anything under src/web, src/templates, src/static, src/adjustments or src/models that a page renders, and before reporting a UI or adjustment change as done.
---

# Verify the Stock Analysis web app

The user-facing surface is a server-rendered web app on localhost. Pages are
Jinja templates; tables are painted client-side from a JSON payload
(`src/static/js/components/table_wiring.js`), and wizard sub-pages save
through `POST /wizard/{TICKER}/{page}/{subpage}`. There is no CLI surface
worth driving and no Playwright in the repo: drive it with the built-in
browser tools (`mcp__Claude_Browser__*`) plus `curl`.

Every command below runs from the repo root. Pick a run id and port once:

```bash
RUN=logs/verify/$(date +%Y%m%d-%H%M%S); PORT=8790
```

`logs/` is gitignored. Use a port other than 8765 (the user's own dev
server from `.claude/launch.json` may be on it).

## Launch

`preview_start {name: "web"}` fails on this Mac with `Operation not
permitted` (macOS blocks the preview launcher from the Documents folder).
Launch from Bash instead, in the background:

```bash
.venv/bin/python .claude/skills/verify/scripts/serve.py "$RUN" "$PORT"
```

Run it with `run_in_background: true`. It copies `data/duckdb/wizard.duckdb`
into `$RUN/wizard.duckdb` and points the app at the copy, so saves never
touch the user's real choices. It refuses a `$RUN` that still holds a DB
copy; use a new `$RUN` or run cleanup first. Ready when this returns `200`:

```bash
until curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/wizard/AAPL" | grep -q 200; do sleep 1; done
```

Then open it: `mcp__Claude_Browser__navigate {url: "http://127.0.0.1:$PORT/..."}`
(substitute the real port; the tool does not expand shell variables).

Statement data comes from the edgartools cache in `data/edgartools_cache/`.
AAPL, MU and SNDK are cached; another ticker triggers a slow SEC download.

## Doctor

Run first, and again whenever anything looks off:

```bash
.claude/skills/verify/scripts/doctor.sh "$RUN"
```

It checks that the pid this run started is alive and owns the port, that `/`
answers as this app, that the run is NOT on the real wizard DB, and that the
git revision and uncommitted `src/` diff match what `serve.py` recorded at
launch. The server keeps the Python it imported, so after any edit under
`src/` it FAILs until you restart (cleanup, then launch). Any `FAIL` means
stop and fix before driving. Never drive a server this run did not start.

## Expected values

Never hardcode a number or a row position from a filing; filings refresh.
Compute what the page should show from the same data, saved choices and
engine the server uses:

```bash
.venv/bin/python .claude/skills/verify/scripts/expected.py "$RUN" AAPL <page> --settings '<drawer JSON>' [--rows id,...] [--js]
```

`<page>` is `assets-in-use`, `fund-flow`, `balance-sheet-size`, `income`,
`balance` or `cashflow`. Read `<drawer JSON>` from the open page:

```js
Object.fromEntries([...document.querySelectorAll('#settings-drawer [name]:not([type=hidden])')].map(e => [e.name, e.value]))
```

Without `--js` it prints JSON (save it as evidence). With `--js` it prints a
`javascript_tool` snippet that compares the open page with those values and
returns `{checked, mismatches, ...}`; a pass is an empty `mismatches`. Use
`--rows` to keep the snippet small when only a few rows matter. Recipes name
which rows and options to pass.

## Drive

Stable handles (from `table_view.js`, `table_wiring.js`, the templates):

- Input cell: `td[data-input-slot][data-row-id="<row id>"][data-col-id="<col>"] input`
  (`type=number` or `type=checkbox`).
- Calculated cell: `td[data-calc-slot][data-row-id="<row id>"][data-col-id="<period>"]`.
- Static cells carry no row id. Rows paint in the order of the `rows` array
  in the table's `<script id="<table id>-data">` JSON; the `expected.py`
  snippet maps rows that way.
- Row ids are statement row ids such as `us-gaap_PropertyPlantAndEquipmentNet`;
  structural rows use lowercase ids (`total_assets`, `owner_earnings`).
- Save: the `Save` button inside `form[data-wizard-save]`; result text in
  `.wizard-save-status` with `data-state="saving"`, then `"saved"` or
  `"error"`. A save takes a few seconds; poll until it leaves `saving`.
- Settings drawer: button with accessible name `Settings`; fields
  `#setting-<id>` (`period`, `num_periods`, `view`, `basis`, ...); the
  `Apply` button submits. Greyed fields are `disabled` with a reason in
  `#setting-<id>-reason`. Settings live in a cookie in the browser pane.
- Adjustments note: `.adjustments-note`.

Use real user actions for anything you are proving: `find` / `read_page` to
get a `ref`, then `computer` `left_click` / `triple_click` + `type` + `Tab`.
The one exception is a native `<select>` (settings drawer): the pane does not
drive its popup by click or keys, so set it with `form_input`, then click
`Apply` for real.

Table inputs have no accessible name and `find` does not match `data-*`
attributes. Refs number elements in document order, so to reach a row's
input: `find "<row label>"` gives the label's ref, and the row's input is the
first ref after it in `find textbox` (number inputs) or `find checkbox`. Pick
rows whose label is unique on the page (`expected.py` names such targets).
After acting, read every input by row and column and confirm the intended
row changed and no other did:

```js
Object.fromEntries([...document.querySelectorAll('td[data-input-slot] input')].map(i => [i.closest('td').dataset.rowId + '/' + i.closest('td').dataset.colId, i.type === 'checkbox' ? i.checked : i.value]))
```

Settings cookies are per host, not per port: a previous run on
`127.0.0.1` leaves its settings in the pane. Open the drawer and check the
baseline values before driving anything period-dependent.
Use `javascript_tool` only to read values out (cell text, input state), never
to set them. Wide tables scroll horizontally inside `.table-wrap`; use
`computer scroll_to` with the ref before clicking an off-screen column.

Feature recipes: [features/README.md](features/README.md).

## Evidence

Write proof into `$RUN/evidence/` (create it):

- `expected.py` output for each check, and the snippet's result, with the
  action that produced the page state (e.g. `aiu-live-gross.expected.json`).
- Server side effects: `.venv/bin/python .claude/skills/verify/scripts/prefs.py "$RUN" AAPL > "$RUN/evidence/prefs.json"`.
- A screenshot of the final state, viewed by you (the browser tool returns
  it inline; describe what it shows in your report).
- `curl -s -o "$RUN/evidence/<page>.html" "http://127.0.0.1:$PORT/<path>"` for
  server-rendered state, plus the server log from the background task.

Proof standards: drive the real user path (inputs, Save, reload), never call
handlers or set model state directly. Capture the action and the resulting
state, and check the side effect (the saved row in `prefs.py`) as well as
the screen. A save is proven only after a reload shows it prefilled.

## Cleanup

```bash
.claude/skills/verify/scripts/stop.sh "$RUN"
```

Kills only the pid this run recorded, deletes the run's DB copy, and keeps
`$RUN/evidence/`. Also stop the background Bash task if it is still listed.
If you changed browser-pane settings (e.g. Basis), set them back through the
drawer. Run cleanup after every failed attempt too.
