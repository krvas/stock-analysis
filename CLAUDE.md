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

Jev (TypeSafe) is available to make typed judgments and choices. The key is
`TYPESAFE_API_KEY` in `.env`. Jev is not a routing step to run before every
choice. Use it for the pstack decisions below, where one Jev call costs far
fewer tokens than reasoning through the choice yourself:

- **Review findings.** `make triage FINDINGS=<path>` scores each finding in
  the bloat-reviewer findings JSON format. It returns `execute` (score of at
  least 0.85, and not `needs_user_decision`) or `human`. Apply `execute`
  findings; show `human` ones to the user.
- **Model tier for a delegate** when `~/.claude/pstack-models.md` does not pin
  the role, or when a step leaves the tier open (for example "trivial
  mechanical edits go to your fast code model"). Run the `jevrouter` skill
  with haiku, sonnet and opus as candidates and pass the returned model to
  the `Agent` call.
- **One pick from a configured pool**, such as the arena cross-judge. Send
  only the pool's models as candidates.

Skip Jev when the config already fixes the choice, when the user named the
tool or model, or when the choice is trivial. If the API fails, decide
yourself and tell the user that Jev was unavailable.

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

Shared files: `src/static/js/components/table_model.js`,
`src/static/js/components/linked_groups.js`,
`src/static/js/components/table_view.js`,
`src/static/js/components/generic_input.js`,
`src/static/js/components/table_wiring.js`, `src/models/table.py`,
`src/web/wizard_registry.py`, `src/web/routes/wizard.py`,
`src/web/settings.py`, `src/web/routes/settings.py`,
`src/web/statements_registry.py`, `src/templates/shared/_page_nav.html`,
`src/templates/shared/_settings_drawer.html`,
`src/templates/shared/_adjustments_note.html`,
`src/static/js/settings_drawer.js`.

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
