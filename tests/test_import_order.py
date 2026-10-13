from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", ["src.web.wizard_registry", "src.web.app"])
def test_module_imports_in_a_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
