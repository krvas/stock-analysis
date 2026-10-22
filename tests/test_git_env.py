"""Every pytest run starts with no ``GIT_*`` variable, however it is launched.

The agent shell exports ``GIT_EDITOR=true``, and under ``git rebase -x`` git
sets ``GIT_DIR``. A test that runs git in a temporary repo inherits them, and
a data test once corrupted this repo's ``.git`` that way.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = """\
import os


def test_no_git_variables():
    assert sorted(k for k in os.environ if k.startswith("GIT_")) == []
"""


def test_pytest_starts_without_git_variables(tmp_path: Path) -> None:
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE)
    env = os.environ | {"GIT_EDITOR": "true", "GIT_DIR": str(tmp_path)}
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        + ["-p", "tests.conftest", str(probe)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
