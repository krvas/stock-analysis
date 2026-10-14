"""Data-test runs share one lock in the main checkout.

Five data-test runs from different worktrees overlapped on a 4-core
machine: load passed 100 and a 1.5 minute run took 39 minutes.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scripts import data_run_lock

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_from_outer_git(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        monkeypatch.delenv(name)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_data_targets_run_pytest_under_the_lock() -> None:
    for target in ("test", "test-data-long"):
        dry_run = subprocess.run(
            ["make", "-n", target], cwd=REPO, check=True, capture_output=True, text=True
        ).stdout
        data_lines = [line for line in dry_run.splitlines() if "-m data" in line]
        assert data_lines, f"make {target} runs no data tests"
        for line in data_lines:
            assert "scripts.data_run_lock" in line, f"make {target}: {line}"


def test_worktrees_share_the_main_checkout_lock(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "root")
    worktree = main / ".claude" / "worktrees" / "w"
    _git(main, "worktree", "add", "-q", str(worktree))
    expected = main.resolve() / ".audit" / "data-run.lock"
    assert data_run_lock.lock_path(worktree).resolve() == expected
    assert data_run_lock.lock_path(main).resolve() == expected


def test_a_second_run_waits_for_the_first(tmp_path: Path) -> None:
    lock = tmp_path / "data-run.lock"
    data_run_lock.acquire(lock, poll_seconds=0.02)
    second = threading.Thread(
        target=data_run_lock.acquire, args=(lock,), kwargs={"poll_seconds": 0.02}
    )
    second.start()
    time.sleep(0.3)
    assert second.is_alive()
    data_run_lock.release(lock)
    second.join(timeout=2)
    assert not second.is_alive()
    data_run_lock.release(lock)
    assert not lock.exists()


def test_a_lock_left_by_a_dead_run_is_taken(tmp_path: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = tmp_path / "data-run.lock"
    lock.mkdir()
    (lock / "pid").write_text(str(dead.pid))
    data_run_lock.acquire(lock, poll_seconds=0.02)
    assert (lock / "pid").read_text() == str(os.getpid())


def _wrapper(lock: Path, *command: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "scripts.data_run_lock", *command],
        cwd=REPO,
        env={**os.environ, "DATA_RUN_LOCK": str(lock)},
        text=True,
    )


def test_the_wrapper_releases_the_lock_and_keeps_the_exit_code(tmp_path: Path) -> None:
    lock = tmp_path / "data-run.lock"
    run = _wrapper(lock, sys.executable, "-c", "raise SystemExit(3)")
    assert run.wait(timeout=10) == 3
    assert not lock.exists()


def test_the_wrapper_releases_the_lock_when_interrupted(tmp_path: Path) -> None:
    lock = tmp_path / "data-run.lock"
    run = _wrapper(lock, sys.executable, "-c", "import time; time.sleep(30)")
    deadline = time.monotonic() + 10
    while not (lock / "pid").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    run.send_signal(signal.SIGTERM)
    run.wait(timeout=10)
    assert not lock.exists()
