# Agent rules for this repo

`specs/STATE.md` is the architecture reference — layout, contracts, hard rules,
what's implemented vs. not. Read it before editing anything you haven't
touched before. This file adds *behavioral* rules on top of it: how to decide
what belongs where, so scope violations don't happen in the first place.

## Checks before every commit

Run `make test` (ruff check, ruff format --check, pytest) from the repo root.
Don't commit code that fails it. `make fix` applies ruff's fixes and formatting.

## Workflow

pstack (`/pstack:poteto-mode`) owns the process for non-trivial work:
playbooks, delegation, review and commits. Where this file and pstack differ
on process, follow pstack. The rules below about where code belongs still
apply inside every pstack step.

## Jev for cheap decisions

A few pstack decisions (review findings, PR review comments, delegate effort
and model tier, arena pre-filter) can go to Jev instead of your own
reasoning. When one comes up, follow the `jev` skill
(`.claude/skills/jev/SKILL.md`).

## The failure mode this file exists to prevent

A prior change hardcoded subpage-specific logic (a dict keyed by the literal
slug `"opex-to-capex"`, containing that subpage's exact save-field mapping)
directly into `src/static/js/line_item_tables.js` — a file `specs/STATE.md`
already documented as required to "stay generic across all wizard subpages
and statement views." The rule existed in writing. It got violated anyway,
because nothing forced a pause at the moment of writing that dict. The
checklist below is the pause. Table hydration for wizard sub-pages and
statement pages now lives in `src/static/js/components/table_wiring.js`; the
same "no subpage-specific logic" rule applies there.

## Before adding code to a shared/generic file

Shared files (one path per bullet; `tests/test_shared_files_stay_generic.py`
reads this list, so add a new shared file here):

- `src/static/js/components/table_model.js`
- `src/static/js/components/linked_groups.js`
- `src/static/js/components/table_view.js`
- `src/static/js/components/generic_input.js`
- `src/static/js/components/table_wiring.js`
- `src/models/table.py`
- `src/web/wizard_registry.py`
- `src/web/routes/wizard.py`
- `src/web/settings.py`
- `src/web/routes/settings.py`
- `src/web/statements_registry.py`
- `src/templates/shared/_page_nav.html`
- `src/templates/shared/_settings_drawer.html`
- `src/templates/shared/_adjustments_note.html`
- `src/static/js/settings_drawer.js`

Before adding a line to one of these, ask: **would this exact line make sense
unchanged for a different subpage, a different statement view, or a table
that doesn't exist yet?** If the answer is no — if it references a specific
subpage slug, a specific field name from one adjustment type, a specific
route, or anything else that only makes sense for the one feature you're
building — it does not belong in that file. It belongs in:

- `src/web/routes/wizard_pages/<name>.py` — subpage-specific context builders
  and POST handlers (data). Hardcoding domain constants for *that specific
  subpage* here is correct, not a violation — these files exist to hold
  exactly that kind of code.
- `src/templates/wizard/<page>/<subpage>.html` — subpage-specific template
  markup.
- `src/web/wizard_registry.py` — identity only (which subpages exist, their
  order, which builder/handler they use). Never data or logic.

This mirrors the rule already in `specs/STATE.md` §4 ("registry = identity,
builders = data") — that rule is about backend subpage wiring; the same
principle applies to the frontend rendering files, which is why it's
restated here explicitly.

## Frontend: table MVC — model owns cells, not the DOM

`TableModel` (`components/table_model.js`) owns cell state:
`fromSerialized`, `getCell`/`setCell`, `subscribe`, `serialize`. It does not
touch the DOM. Linked-group math runs in `components/linked_groups.js` and
is invoked from the model on `setCell`.

`table_view.js` only paints via `render_table(container, table)`. It does
not read or write input element state and does not attach listeners. Input
columns are empty slots in the markup.

`generic_input.js` is the only file that creates table-input event handlers
and the only file that reads or writes that input's DOM value (`GenericInput`).

`table_wiring.js` subscribes each `GenericInput` to the model and the model
back to the input (`input.subscribe` → `setCell`; `model.subscribe` →
`input.set`). It must not scrape `input.value` / `input.checked`. Save uses
`model.serialize()`.

`Table.serialize()` (Python) and `TableModel.serialize()` (JS) are
**intentionally asymmetric** — see `specs/STATE.md` §5. Do not "fix"
`TableModel.serialize()` to mirror `Table.serialize()`'s full shape; they
serve different directions (receive vs. send) on purpose.

## Generic rule for any new abstraction

If a class/module exists specifically to own a responsibility (e.g.
`TableModel` owning client-side table state), and you're about to duplicate
that responsibility elsewhere (re-deriving the same data by hand, scraping
the DOM again, re-shaping a payload a different way) — stop and use the
existing owner instead, or explain in the commit message why it doesn't fit
and what should change about it. Don't leave a second, informal
implementation of the same job sitting next to the real one.

## Dead code with a stated reason is still worth double-checking

`specs/STATE.md` sometimes describes something as deliberately unfinished
("not wired to DOM yet", "no UI", etc.). Before treating that as settled,
check whether it's still true — a doc note can describe a real deferral or it
can be quietly documenting a shortcut nobody corrected. If you're not sure
which, ask rather than assuming the doc's framing is still accurate.

## Rules from operator corrections

Each rule a correction produced, and what enforces it. A rule with nothing
enforcing it is a repeat waiting to happen: encode it before adding another.

| Rule | Enforced by |
| --- | --- |
| The app, its browser-pane server and agent worktrees run from this repo folder, never from a sibling folder (e.g. `../<name>` under `~/Documents`). Worktrees go in `.claude/worktrees/<name>` (gitignored); the app starts through `.claude/skills/verify/scripts/serve.py` or the `web` entry in `.claude/launch.json`. | `scripts/stay_in_repo.py`: a Bash `PreToolUse` hook in `.claude/settings.json` blocks out-of-repo `git worktree add` and app launches; `tests/test_stay_in_repo.py` fails on a `.claude/launch.json` entry that leaves the repo. |
| A threshold pair that mirrors itself (execute at `1 - x`, drop at `x`) is one constant, not two. Jev's tunables sit at the top of `scripts/jev_decide.py` and each reads a `JEV_` override from `.env`. | `FINDINGS_MARGIN` is the only findings threshold. In `tests/test_jev_decide.py`, `test_every_tunable_reads_the_environment` fails on a module-level number not read through `_setting`, and `test_one_margin_sets_both_finding_thresholds` fails when the pair drifts apart. |
| A worktree sees the main checkout's gitignored local files (`.env`, the data-test ticker lists, `.venv`, `node_modules`, the edgartools cache, test fixtures under `data/raw`) as symlinks, so tests behave the same there. Add a newly needed local file to the one tuple, never copy it. | `scripts/link_worktree_files.py` (`LINKED_PATHS`), run first by `make test`; `tests/test_link_worktree_files.py` checks it against a real `git worktree add`. |
| Shared files name no sub-page: no sub-page slug, adjustment type id or builder column id in a file on the shared-file list above (the registry itself excepted). Only `generic_input.js` attaches table-input listeners; other components listen only to a literal non-edit event such as `"submit"`. `table_wiring.js` and `table_view.js` never touch `.value` / `.checked`; `table_view.js` attaches no listeners. | `tests/test_shared_files_stay_generic.py` reads the shared-file list from this file (failing if it cannot parse it or a path is missing), derives the forbidden names from `src/web/wizard_registry.py`, `src/adjustments/registry.py` and the `ColumnSpec` ids under `src/web/routes/wizard_pages/`, and scans each shared file; `make test` fails with the rule and the right home for the code. Single-word names (`value`, `moats`) are not scanned. |
| `make test` and `make test-data-long` run pytest with no `GIT_*` variable; no need to unset them by hand. | The `Makefile`'s `NO_GIT_ENV` prefix on every pytest line; `tests/test_makefile.py` runs each pytest line of `make -n` for both targets with `GIT_EDITOR` and `GIT_DIR` set and fails if pytest would see them. |
