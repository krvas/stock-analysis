from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "link_worktree_files.py"
GITIGNORE = Path(__file__).resolve().parents[1] / ".gitignore"
LOCAL_FILES = {
    ".env": "EDGAR_IDENTITY=test@example.com\n",
    ".venv/pyvenv.cfg": "home = /usr\n",
    "node_modules/.package-lock.json": "{}\n",
    "tests/data_test_tickers.txt": "AAPL\n",
    "data/edgartools_cache/company_lru.json": "{}\n",
    "data/raw/finnhub/financials_reported_AMD.json": "{}\n",
}
LINKS = [".env", ".venv", "node_modules", "tests/data_test_tickers.txt"]
LINKS += ["data/edgartools_cache", "data/raw/finnhub/financials_reported_AMD.json"]


@pytest.fixture(autouse=True)
def _isolate_from_outer_git(monkeypatch: pytest.MonkeyPatch) -> None:
    # Under `git rebase -x` or a git hook, GIT_DIR / GIT_INDEX_FILE point at
    # the real repo; inherited, they turn the temp repo's init and worktree
    # add into writes to the user's .git.
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        monkeypatch.delenv(name)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _run(cwd: Path) -> str:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, Path]:
    """A main checkout with the repo's .gitignore and local files, plus a worktree."""
    main = tmp_path / "main"
    (main / "tests").mkdir(parents=True)
    (main / ".gitignore").write_text(GITIGNORE.read_text())
    (main / "tests" / "keep.py").write_text("")
    _git(main, "init", "-q")
    _git(main, "add", ".")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    for rel, text in LOCAL_FILES.items():
        (main / rel).parent.mkdir(parents=True, exist_ok=True)
        (main / rel).write_text(text)
    worktree = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", str(worktree))
    return main, worktree


def test_links_local_files_into_worktree(checkout: tuple[Path, Path]) -> None:
    main, worktree = checkout
    _run(worktree / "tests")
    for rel in LINKS:
        assert (worktree / rel).is_symlink(), rel
    for rel, text in LOCAL_FILES.items():
        assert (worktree / rel).resolve() == (main / rel).resolve(), rel
        assert (worktree / rel).read_text() == text, rel
    assert not (worktree / "tests/data_test_tickers_long.txt").exists()
    assert _git(worktree, "status", "--porcelain") == ""


def test_rerun_is_a_no_op(checkout: tuple[Path, Path]) -> None:
    _, worktree = checkout
    _run(worktree)
    before = {rel: (worktree / rel).readlink() for rel in LINKS}
    out = _run(worktree)
    assert "linked" not in out
    assert {rel: (worktree / rel).readlink() for rel in LINKS} == before


def test_real_file_is_not_clobbered(checkout: tuple[Path, Path]) -> None:
    _, worktree = checkout
    (worktree / ".env").write_text("MINE=1\n")
    out = _run(worktree)
    assert not (worktree / ".env").is_symlink()
    assert (worktree / ".env").read_text() == "MINE=1\n"
    assert "kept existing .env" in out


def test_main_checkout_is_a_no_op(checkout: tuple[Path, Path]) -> None:
    main, _ = checkout
    before = sorted(
        p.relative_to(main) for p in main.rglob("*") if ".git" not in p.parts
    )
    assert _run(main) == ""
    after = sorted(
        p.relative_to(main) for p in main.rglob("*") if ".git" not in p.parts
    )
    assert after == before
    assert not any(p.is_symlink() for p in main.rglob("*"))
