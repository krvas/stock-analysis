# Rules from operator corrections

Each rule a correction produced, and what enforces it. A rule with nothing
enforcing it is a repeat waiting to happen: encode it before adding another.
Delete a row once its mistake can't happen.

| Rule | Enforced by |
| --- | --- |
| Never `git stash` in an agent worktree: `refs/stash` is shared by every worktree, so parallel agents pop and drop each other's entries. Save a patch (`git diff > <scratchpad>/wip.patch`, then `git apply`) or make a WIP commit. | `scripts/stay_in_repo.py` (the Bash `PreToolUse` hook) refuses a `git worktree add` outside `.claude/worktrees/`, and a `git stash` that writes `refs/stash` when it runs there (cwd, `cd` or `git -C`); `tests/test_stay_in_repo.py` replays the stashes agents ran. |
| Jev's decision log outlives the worktree that wrote it: every run appends to the main checkout's `logs/jev/decisions.jsonl`. | `scripts/jev_decide.py` resolves `LOG_PATH` from `git rev-parse --git-common-dir`; `test_a_run_from_a_worktree_logs_to_the_main_checkout` in `tests/test_jev_decide.py` runs from a real worktree. |
| Log every playbook pick, for yourself or a delegate, through the `jev` skill, and tell a delegate that triages review findings to use it. Without `scripts/jev_decide.py` on the branch, say that Jev is unavailable. | The `jev` skill's description opens with those triggers; `test_skill_description_leads_with_the_missed_triggers` in `tests/test_jev_decide.py` fails if an edit buries them. Nothing forces the skill to load: this stays a judgment rule. |
| `make test` runs pytest with no `GIT_*` variable; no need to unset them by hand. | The `Makefile`'s `NO_GIT_ENV` prefix on every pytest line; `tests/test_makefile.py` runs each pytest line of `make -n test` with `GIT_EDITOR` and `GIT_DIR` set and fails if pytest would see them. |
