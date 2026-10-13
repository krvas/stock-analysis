---
name: jev
description: Hand a few cheap pstack decisions to Jev (TypeSafe) instead of reasoning through them - triaging bloat-reviewer findings, classifying PR review comments during Babysit, logging a playbook pick, picking a delegate's reasoning effort, pre-filtering arena candidates, and picking a delegate's model tier. Use when one of those decisions comes up in this repo.
---

# Jev for cheap decisions

Jev (TypeSafe) makes typed judgments and choices. The key is
`TYPESAFE_API_KEY` in `.env`. Jev is not a routing step to run before every
choice. Use it for the decisions below, where one Jev call costs far fewer
tokens than reasoning through the choice yourself.

Each runs as `make jev KIND=<kind> INPUT=<path.json>`. It writes
`<input stem>.jev.json` beside the input and logs every result to
`logs/jev/decisions.jsonl`. `scripts/jev_decide.py --help` lists each kind's
input format. The thresholds and API settings sit at the top of that script;
override any of them from `.env` with its `JEV_` variable.

## What to do with each decision

- **Review findings** (`findings`): `execute` (score of at least
  1 - `JEV_FINDINGS_MARGIN`, 0.85 by default), `drop` (at most the margin) or
  `human`; a finding marked `needs_user_decision` is always `human`. Apply
  `execute` findings, discard `drop` ones, and show `human` ones to the user.
- **PR review comments** during Babysit (`comments`). A human comment is
  `mechanical` (make the edit) or `judgment` (leave the code, reply with what
  you would do). A bot comment is `fix`, `dismiss` or `ask`, per pstack's
  bugbot triage rubric: fix it, reply with the reason and resolve, or ask the
  user.
- **Playbook pick** (`playbook`). Log only. Pick the playbook yourself first,
  pass your pick as `agent_choice`, and follow your pick, not Jev's. The log
  records whether Jev agreed.
- **Reasoning effort for a delegate** (`effort`). Returns a level (`low` to
  `xhigh`) or `session`. A level picks the `pstack:poteto-agent-<level>` or
  `pstack:effort-<level>` agent per pstack's Reasoning effort rules; `session`
  means the usual agent. Skip it when the override sheet pins a level for the
  role.
- **Arena pre-filter** (`arena`). Returns `exclude` for a candidate that is
  obviously broken and `keep` otherwise. The judge skips `exclude`
  candidates. Jev never picks the base or ranks the rest.
- **Model tier for a delegate** when `~/.claude/pstack-models.md` does not pin
  the role, or when a step leaves the tier open (for example "trivial
  mechanical edits go to your fast code model"). Run the `jevrouter` skill
  with haiku, sonnet and opus as candidates and pass the returned model to
  the `Agent` call.
- **One pick from a configured pool**, such as the arena cross-judge. Run
  `jevrouter` with only the pool's models as candidates.

## When to skip it

Skip Jev when the config already fixes the choice, when the user named the
tool or model, or when the choice is trivial. If the API fails, decide
yourself and tell the user that Jev was unavailable.
