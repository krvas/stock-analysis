"""``make test`` and ``make test-data-long`` run pytest with no ``GIT_*``
variable in its environment.

The agent shell exports ``GIT_EDITOR=true``, and under ``git rebase -x`` git
sets ``GIT_DIR``. A test that runs git in a temporary repo inherits them, and
a data test once corrupted this repo's ``.git`` that way.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_PRINT_GIT_VARS = (
    "-c 'import os; print(sorted(k for k in os.environ if k.startswith(\"GIT_\")))'"
)


def _pytest_commands(target: str, env: dict[str, str]) -> list[str]:
    dry_run = subprocess.run(
        ["make", "-n", target],
        cwd=REPO,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.replace("\\\n", " ")
    return [line for line in dry_run.splitlines() if " -m pytest" in line]


@pytest.mark.parametrize("target", ["test", "test-data-long"])
def test_pytest_sees_no_git_variables(target: str, tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MAKE", "MFLAGS"))}
    env |= {"GIT_EDITOR": "true", "GIT_DIR": str(tmp_path / "git")}
    env["DATA_RUN_LOCK"] = str(tmp_path / "data-run.lock")
    commands = _pytest_commands(target, env)
    assert commands, f"make {target} runs no pytest command"
    for command in commands:
        launcher = command.split(" -m pytest")[0]
        seen = subprocess.run(
            ["sh", "-c", f"{launcher} {_PRINT_GIT_VARS}"],
            cwd=REPO,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert seen == "[]", f"`{command}` passes {seen} to pytest"
