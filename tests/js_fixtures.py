"""Committed page payloads that ``tests/js/calculated_cell.test.js`` evaluates."""

from __future__ import annotations

import json
import os
from pathlib import Path

FIXTURES = Path(__file__).parent / "js" / "fixtures"


def check_calculated_cells_fixture(
    name: str, table: dict, expected: dict[tuple[str, str], float]
) -> None:
    """Assert ``tests/js/fixtures/<name>`` holds ``table`` and the engine's
    ``(row_id, col_id) -> value``; ``UPDATE_JS_FIXTURES=1`` rewrites it."""
    path = FIXTURES / name
    fixture = {
        "table": table,
        "expected": [
            {"row_id": row, "col_id": col, "value": value}
            for (row, col), value in expected.items()
        ],
    }
    text = json.dumps(fixture, indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_JS_FIXTURES"):
        path.write_text(text)
    assert path.read_text() == text, f"{path} is stale: rerun with UPDATE_JS_FIXTURES=1"
