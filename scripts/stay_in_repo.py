"""Keep the app and its working copies inside the repo folder.

Two checks share one notion of "inside the repo":

- ``command_violation``: a Claude Code ``PreToolUse`` hook on Bash (wired in
  ``.claude/settings.json``) refuses a command that adds a git worktree
  outside the repo or starts the web app from outside it.
- ``launch_config_violations``: ``tests/test_stay_in_repo.py`` fails when a
  ``.claude/launch.json`` entry would start the browser pane's server outside
  the repo.

Usage as a hook: reads the hook JSON on stdin; exit 2 with the reason on
stderr blocks the command.

Not part of the app package.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

WORKTREE_FIX = (
    "create worktrees inside the repo: "
    "git worktree add .claude/worktrees/<name> -b <branch> <base> (gitignored)"
)
LAUNCH_FIX = (
    "run the app from the repo root: "
    ".venv/bin/python .claude/skills/verify/scripts/serve.py <run dir> <port> "
    "(see .claude/skills/verify/SKILL.md), or the `web` entry in .claude/launch.json"
)
_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")"})
_SHELLS = frozenset({"bash", "sh", "zsh"})
_APP_MARKERS = ("uvicorn", "serve.py", "src.web.app:app")
_WORKTREE_OPTIONS_WITH_VALUE = frozenset({"-b", "-B", "--reason"})


def _inside(path: Path, repo: Path) -> bool:
    # Lexical, not resolve(): .venv/bin/python is a symlink out of the repo.
    normal = Path(os.path.normpath(path.absolute()))
    return normal.is_relative_to(os.path.normpath(repo.absolute()))


def _segments(command: str) -> Iterator[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segment: list[str] = []
    for token in lexer:
        if token in _SEPARATORS:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def _worktree_target(segment: list[str]) -> str | None:
    if segment[:3] != ["git", "worktree", "add"]:
        return None
    args = iter(segment[3:])
    for arg in args:
        if arg in _WORKTREE_OPTIONS_WITH_VALUE:
            next(args, None)
        elif not arg.startswith("-"):
            return arg
    return None


def _launches_app(segment: list[str]) -> bool:
    return any(token.endswith(_APP_MARKERS) for token in segment)


def command_violation(command: str, cwd: Path, repo: Path) -> str | None:
    """Why ``command``, run in ``cwd``, takes the app outside ``repo``; or None."""
    try:
        segments = list(_segments(command))
    except ValueError:
        return None
    for segment in segments:
        if segment[0] == "cd":
            cwd = cwd / segment[1] if len(segment) > 1 else Path.home()
            continue
        if segment[0] in _SHELLS and "-c" in segment[:-1]:
            script = segment[segment.index("-c") + 1]
            if reason := command_violation(script, cwd, repo):
                return reason
            continue
        target = _worktree_target(segment)
        if target is not None and not _inside(cwd / target, repo):
            return f"worktree {target!r} is outside {repo}; {WORKTREE_FIX}"
        if _launches_app(segment):
            if not _inside(cwd, repo):
                return f"starts the app from {os.path.normpath(cwd.absolute())}; {LAUNCH_FIX}"
            for token in segment:
                if "/" in token and not _inside(cwd / token, repo):
                    return f"starts the app from {token!r}; {LAUNCH_FIX}"
    return None


def launch_config_violations(config: Mapping[str, Any], repo: Path) -> list[str]:
    """One message per ``launch.json`` configuration that leaves ``repo``."""
    problems = []
    for entry in config.get("configurations", []):
        name = entry.get("name", "?")
        executable = entry.get("runtimeExecutable", "")
        if Path(executable).name in _SHELLS:
            problems.append(f"{name}: wraps the server in a shell; {LAUNCH_FIX}")
            continue
        if Path(executable).is_absolute() or not (repo / executable).exists():
            problems.append(
                f"{name}: {executable!r} is not a path inside the repo; {LAUNCH_FIX}"
            )
        for arg in entry.get("runtimeArgs", []):
            if Path(arg).is_absolute() or ".." in Path(arg).parts:
                problems.append(f"{name}: argument {arg!r} leaves the repo")
    return problems


def main() -> int:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    repo = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).parents[1])
    cwd = Path(event.get("cwd") or os.getcwd())
    reason = command_violation(command, cwd, repo)
    if reason is None:
        return 0
    print(f"Blocked: {reason}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
