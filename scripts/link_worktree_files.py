"""Symlink the main checkout's gitignored local files into a git worktree.

A fresh worktree has none of the untracked files the app and ``make test``
read (``.env``, the data-test ticker lists, the shared edgartools cache, ...),
so tests skip or fail there that pass in the main checkout. Run from anywhere
inside a worktree; it is a no-op in the main checkout. Stdlib only, because it
runs before ``.venv`` is linked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LINKED_PATHS = (
    ".env",
    ".venv",
    "node_modules",
    "tests/data_test_tickers.txt",
    "tests/data_test_tickers_long.txt",
    "data/edgartools_cache",
    "data/raw/finnhub/financials_reported_AMD.json",
)


def _git_path(cwd: Path, *args: str) -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return Path(out.strip())


def main_checkout(cwd: Path) -> Path:
    """The root of the main checkout that ``cwd`` (maybe a worktree) belongs to."""
    return _git_path(cwd, "--git-common-dir").parent


def link_worktree_files(cwd: Path) -> list[str]:
    """Link each of ``LINKED_PATHS`` that the main checkout has; return notes."""
    common_dir = _git_path(cwd, "--git-common-dir")
    if _git_path(cwd, "--git-dir") == common_dir:
        return []
    main_root = common_dir.parent
    worktree_root = _git_path(cwd, "--show-toplevel")
    notes = []
    for rel in LINKED_PATHS:
        source = main_root / rel
        target = worktree_root / rel
        if target.is_symlink() and target.readlink() == source:
            continue
        if target.exists() or target.is_symlink():
            notes.append(f"kept existing {rel}")
            continue
        if not source.exists():
            notes.append(f"main checkout has no {rel}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)
        notes.append(f"linked {rel}")
    return notes


def main() -> int:
    for note in link_worktree_files(Path.cwd()):
        print(f"link_worktree_files: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
