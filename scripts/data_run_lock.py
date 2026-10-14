"""Run a command while holding the shared data-test lock.

Usage (from the repo root): ``python3 -m scripts.data_run_lock <command...>``.

Data tests load several companies' filings each; runs from parallel worktrees
on one machine starve each other (five overlapping runs took a 1.5 minute
run to 39 minutes). Every worktree resolves the same lock, the directory
``.audit/data-run.lock`` in the main checkout (``DATA_RUN_LOCK`` overrides
it), and a run waits until it can create that directory. The lock holds a
``pid`` file; a lock whose pid is gone is taken over. A lock without one was
taken by hand (``mkdir`` ... ``rmdir``) and is waited on. Stdlib only, like
``link_worktree_files``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from scripts.link_worktree_files import main_checkout

POLL_SECONDS = 30


def lock_path(cwd: Path) -> Path:
    """The lock every checkout of the repo that ``cwd`` is in shares."""
    if override := os.environ.get("DATA_RUN_LOCK"):
        return Path(override)
    return main_checkout(cwd) / ".audit" / "data-run.lock"


def _holder(lock: Path) -> int | None:
    try:
        return int((lock / "pid").read_text())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire(lock: Path, poll_seconds: float = POLL_SECONDS) -> None:
    """Create ``lock``, waiting while another live run holds it."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    waiting = False
    while True:
        try:
            lock.mkdir()
        except FileExistsError:
            holder = _holder(lock)
            if holder is not None and not _alive(holder):
                print(f"data_run_lock: taking {lock} from dead pid {holder}")
                release(lock)
                continue
            if not waiting:
                print(
                    f"data_run_lock: waiting for {lock} (pid {holder or '?'}); "
                    "remove it if no data run is going",
                    file=sys.stderr,
                )
                waiting = True
            time.sleep(poll_seconds)
        else:
            (lock / "pid").write_text(str(os.getpid()))
            return


def release(lock: Path) -> None:
    (lock / "pid").unlink(missing_ok=True)
    lock.rmdir()


def run(command: list[str], lock: Path) -> int:
    """Run ``command`` under ``lock``; return its exit code."""
    child: subprocess.Popen[bytes] | None = None

    def stop(signum: int, frame: object) -> None:
        if child is None:
            raise SystemExit(128 + signum)
        child.send_signal(signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    acquire(lock)
    try:
        child = subprocess.Popen(command)
        while True:
            try:
                code = child.wait()
                break
            except KeyboardInterrupt:
                continue  # Ctrl-C reaches the child too; wait for it to stop.
    finally:
        release(lock)
    return 128 - code if code < 0 else code


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    return run(argv, lock_path(Path.cwd()))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
