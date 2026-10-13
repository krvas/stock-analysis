"""Serve the app for one verification run, on its own port and wizard DB copy.

Usage: .venv/bin/python .claude/skills/verify/scripts/serve.py RUN_DIR PORT

Saves from wizard sub-pages land in RUN_DIR/wizard.duckdb, never in
data/duckdb/wizard.duckdb, so a run can't change the user's saved choices.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import uvicorn

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from src.config import DEFAULT_WIZARD_DB_PATH
from src.database import wizard_manager

run_dir = Path(sys.argv[1]).resolve()
port = int(sys.argv[2])
run_dir.mkdir(parents=True, exist_ok=True)
db = run_dir / "wizard.duckdb"
if not db.exists() and DEFAULT_WIZARD_DB_PATH.exists():
    shutil.copy2(DEFAULT_WIZARD_DB_PATH, db)
wizard_manager.DEFAULT_WIZARD_DB_PATH = db
(run_dir / "server.pid").write_text(str(os.getpid()))
(run_dir / "server.json").write_text(
    f'{{"port": {port}, "wizard_db": "{db}", "pid": {os.getpid()}}}\n'
)
print(f"verify: wizard DB {db}", flush=True)

uvicorn.run("src.web.app:app", host="127.0.0.1", port=port, log_level="info")
