"""Keep the app and its working copies inside the repo folder.

Two checks share one notion of "inside the repo":

- ``command_violation``: a Claude Code ``PreToolUse`` hook on Bash (wired in
  ``.claude/settings.json``) refuses a command that adds a git worktree
  outside the repo or starts the web app from outside it. It also refuses
  ``git stash`` inside an agent worktree: ``refs/stash`` is shared by every
  worktree, so parallel agents pop and drop each other's entries.
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
import re
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
STASH_FIX = (
    "refs/stash is shared by every worktree, so another agent can pop or drop "
    "this entry; save the change as a patch instead "
    "(git diff > <scratchpad>/wip.patch, later git apply <scratchpad>/wip.patch) "
    "or make a WIP commit (git commit -m wip, later git reset HEAD~)"
)
_SEPARATOR_CHARS = frozenset("&|;()\n")
_SHELLS = frozenset({"bash", "sh", "zsh"})
_APP_PROGRAMS = frozenset({"uvicorn", "serve.py"})
_COMMAND_PREFIXES = frozenset({"exec", "nohup", "env", "time", "command", "sudo"})
_SHELL_KEYWORDS = frozenset(
    {"if", "then", "elif", "else", "do", "while", "until", "{", "!"}
)
_HEREDOC = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)(\w+)\2")
_WORKTREE_OPTIONS_WITH_VALUE = frozenset({"-b", "-B", "--reason"})
_GIT_OPTIONS_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
)
_READ_ONLY_STASH = frozenset({"list", "show"})


def _inside(path: Path, repo: Path) -> bool:
    # Lexical, not resolve(): .venv/bin/python is a symlink out of the repo.
    normal = Path(os.path.normpath(path.absolute()))
    return normal.is_relative_to(os.path.normpath(repo.absolute()))


def _without_heredoc_bodies(command: str) -> str:
    kept: list[str] = []
    pending: list[tuple[bool, str]] = []
    for line in command.split("\n"):
        if pending:
            strip_tabs, word = pending[0]
            if (line.lstrip("\t") if strip_tabs else line) == word:
                pending.pop(0)
            continue
        kept.append(line)
        pending = [(dash == "-", word) for dash, _, word in _HEREDOC.findall(line)]
    return "\n".join(kept)


def _segments(command: str) -> Iterator[list[str]]:
    text = _without_heredoc_bodies(command).replace("\\\n", " ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    segment: list[str] = []
    for token in lexer:
        if set(token) <= _SEPARATOR_CHARS:
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


def _in_agent_worktree(path: Path) -> bool:
    parts = Path(os.path.normpath(path.absolute())).parts
    return any(
        parts[i : i + 2] == (".claude", "worktrees") for i in range(len(parts) - 2)
    )


def _program_words(segment: list[str]) -> list[str]:
    """``segment`` from the program it runs: no prefix, assignment or keyword."""
    words = list(segment)
    while words and (
        words[0] in _COMMAND_PREFIXES or words[0] in _SHELL_KEYWORDS or "=" in words[0]
    ):
        words.pop(0)
    return words


def _git_stash_cwd(segment: list[str], cwd: Path) -> Path | None:
    """The directory a ``git stash`` that writes refs/stash runs in; or None."""
    words = _program_words(segment)
    if not words or Path(words[0]).name != "git":
        return None
    args = iter(words[1:])
    for arg in args:
        if arg == "-C":
            cwd = cwd / next(args, "")
        elif arg in _GIT_OPTIONS_WITH_VALUE:
            next(args, None)
        elif not arg.startswith("-"):
            if arg != "stash":
                return None
            action = next(args, "push")
            return None if action in _READ_ONLY_STASH else cwd
    return None


def _launches_app(segment: list[str]) -> bool:
    words = _program_words(segment)
    if words and Path(words[0]).name.startswith("python"):
        words = [word for word in words[1:] if not word.startswith("-")]
    return bool(words) and Path(words[0]).name in _APP_PROGRAMS


def command_violation(command: str, cwd: Path, repo: Path) -> str | None:
    """Why ``command``, run in ``cwd``, is refused (leaves ``repo`` or stashes
    in an agent worktree); or None."""
    try:
        segments = list(_segments(command))
    except ValueError:
        # Bash runs every complete line before the one it cannot parse.
        lines = command.splitlines()
        for line in lines if len(lines) > 1 else []:
            if reason := command_violation(line, cwd, repo):
                return reason
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
        stash_cwd = _git_stash_cwd(segment, cwd)
        if stash_cwd is not None and _in_agent_worktree(stash_cwd):
            return f"git stash in worktree {os.path.normpath(stash_cwd)}; {STASH_FIX}"
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
