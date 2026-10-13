"""Print a run's saved adjustment preferences (read-only) as JSON.

Usage: .venv/bin/python .claude/skills/verify/scripts/prefs.py RUN_DIR [TICKER]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

db = Path(sys.argv[1]) / "wizard.duckdb"
ticker = sys.argv[2].upper() if len(sys.argv) > 2 else None
con = duckdb.connect(str(db), read_only=True)
query = (
    "select ticker, adjustment_type, base_concept, value from adjustment_preferences"
)
rows = con.execute(
    query + (" where ticker = ?" if ticker else "") + " order by 1, 2, 3",
    [ticker] if ticker else [],
).fetchall()
keys = ("ticker", "adjustment_type", "base_concept", "value")
print(json.dumps([dict(zip(keys, row, strict=True)) for row in rows], indent=1))
