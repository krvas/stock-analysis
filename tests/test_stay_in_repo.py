from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.stay_in_repo import command_violation, launch_config_violations

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "scripts" / "stay_in_repo.py"

# Commands and the launch entry agents actually ran on 2026-10-10.
PAST_WORKTREE = (
    'git worktree add "../stock-analysis-wt-settings" '
    "-b feat/shared-nav-and-settings HEAD"
)
PAST_LAUNCH = (
    "cd ../stock-analysis-wt-settings && exec .venv/bin/uvicorn "
    "src.web.app:app --port 8766"
)
SERVE = ".claude/skills/verify/scripts/serve.py"
# A commit message that mentions the launcher, refused as a launch until 2026-10-13.
PAST_COMMIT = f"git commit -F - <<'EOF'\nchore: add {SERVE} launcher / helper\nEOF"
# Parallel agents ran these in their worktrees on 2026-10-13 and popped each
# other's entries from the shared refs/stash, dropping the operator's stash.
# A fixed path: the suite itself may run from an agent worktree.
MAIN = Path("/Users/agent/Stock Analysis")
WORKTREE = MAIN / ".claude" / "worktrees" / "fu-6"
PAST_STASHES = [
    "git stash",
    "git stash push -m 'wip before rebase'",
    "git stash pop",
    "git stash drop",
    f'git -C "{WORKTREE}" stash apply',
]
# The same stash behind a prefix, an assignment or a shell keyword.
PREFIXED_STASHES = [
    "GIT_EDITOR=true git stash pop",
    "env git stash",
    "command git stash",
    "time git stash",
    "nohup git stash",
    "exec git stash",
    "sudo git stash",
    "if true; then git stash; fi",
    "{ git stash; }",
    "! git stash",
    "for i in 1; do git stash; done",
]
PAST_LAUNCH_ENTRY = {
    "name": "web-settings-wt",
    "runtimeExecutable": "bash",
    "runtimeArgs": ["-c", PAST_LAUNCH],
    "port": 8766,
}


@pytest.mark.parametrize(
    "command",
    [
        PAST_WORKTREE,
        PAST_LAUNCH,
        f"bash -c {json.dumps(PAST_LAUNCH)}",
        "git worktree add /tmp/elsewhere HEAD",
        "git worktree add scratch/w -b x",
        "../stock-analysis-wt-settings/.venv/bin/uvicorn src.web.app:app",
        "cd && .venv/bin/python .claude/skills/verify/scripts/serve.py r 8790",
        f"cd /tmp\n.venv/bin/python {SERVE} r 8790",
        f"cat > m.txt <<'EOF'\nnotes\nEOF\ncd .. && exec .venv/bin/python -u {SERVE} r 8790",
        "cd /tmp && PORT=1 nohup python3 -m uvicorn src.web.app:app",
    ],
)
def test_commands_that_leave_the_repo_are_refused(command: str) -> None:
    assert command_violation(command, REPO, REPO) is not None


@pytest.mark.parametrize(
    "command",
    [
        "git worktree add .claude/worktrees/settings -b feat/x HEAD",
        ".venv/bin/uvicorn src.web.app:app --port 8765",
        ".venv/bin/python .claude/skills/verify/scripts/serve.py logs/verify/1 8790",
        f'cd "{REPO}" && exec .venv/bin/uvicorn src.web.app:app --port 8765',
        "cd ../other-project && make test",
        "git worktree list",
        PAST_COMMIT,
        f"git commit -m 'add {SERVE}' -m 'see /docs'",
        f"grep -n {SERVE} /tmp/hook.log",
    ],
)
def test_commands_inside_the_repo_are_allowed(command: str) -> None:
    assert command_violation(command, REPO, REPO) is None


@pytest.mark.parametrize("command", PAST_STASHES + PREFIXED_STASHES)
def test_stash_in_an_agent_worktree_is_refused(command: str) -> None:
    reason = command_violation(command, WORKTREE, MAIN)
    assert reason is not None
    assert "git diff" in reason and "WIP commit" in reason


def test_stash_into_a_worktree_with_dash_c_is_refused() -> None:
    command = "git -C .claude/worktrees/fu-6 stash clear"
    assert command_violation(command, MAIN, MAIN) is not None
    assert command_violation(f"cd '{WORKTREE}' && git stash", MAIN, MAIN) is not None


def test_a_stash_before_an_unparseable_line_is_refused() -> None:
    """Bash runs every complete line before the one with an open quote."""
    assert command_violation("git stash\necho 'x", WORKTREE, MAIN) is not None
    assert command_violation("echo 'x", WORKTREE, MAIN) is None


@pytest.mark.parametrize(
    ("command", "cwd"),
    [
        ("git stash list", WORKTREE),
        ("git stash show -p stash@{0}", WORKTREE),
        ("git status", WORKTREE),
        ("git stash", MAIN),
    ],
)
def test_read_only_stash_and_main_checkout_stash_are_allowed(
    command: str, cwd: Path
) -> None:
    assert command_violation(command, cwd, MAIN) is None


def test_refusal_names_the_supported_path() -> None:
    assert ".claude/worktrees" in command_violation(PAST_WORKTREE, REPO, REPO)
    assert "serve.py" in command_violation(PAST_LAUNCH, REPO, REPO)


def test_repo_launch_config_stays_in_repo() -> None:
    config = json.loads((REPO / ".claude" / "launch.json").read_text())
    assert launch_config_violations(config, REPO) == []


def test_past_launch_entry_is_refused() -> None:
    config = {"configurations": [PAST_LAUNCH_ENTRY]}
    assert launch_config_violations(config, REPO)


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(REPO)}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(REPO)},
        check=False,
    )


def test_hook_blocks_with_exit_2_and_allows_with_0() -> None:
    blocked = _run_hook(PAST_WORKTREE)
    assert blocked.returncode == 2
    assert ".claude/worktrees" in blocked.stderr
    assert _run_hook("git status").returncode == 0


def test_hook_is_wired_for_bash() -> None:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry["matcher"] == "Bash"
        for hook in entry["hooks"]
    ]
    assert any("scripts/stay_in_repo.py" in command for command in commands)
