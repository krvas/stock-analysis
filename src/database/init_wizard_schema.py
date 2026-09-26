"""Initialize the wizard DuckDB schema from wizard.sql.

Run directly:
    python -m src.database.init_wizard_schema
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.config import DEFAULT_WIZARD_DB_PATH, WIZARD_SCHEMA_SQL_PATH
from src.database.wizard_manager import WizardDatabaseManager

logger = logging.getLogger(__name__)


def initialize_wizard_schema(
    db_path: Path | None = None,
    schema_path: Path | None = None,
) -> Path:
    """Create wizard database file and apply DDL."""
    db_path = (db_path or DEFAULT_WIZARD_DB_PATH).resolve()
    schema_path = (schema_path or WIZARD_SCHEMA_SQL_PATH).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    logger.info("Initializing wizard DuckDB at %s", db_path)
    with WizardDatabaseManager(db_path, auto_connect=True) as db:
        db.initialize_schema(schema_path)
        logger.info("Created tables: %s", db.list_tables())

    return db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize wizard DuckDB schema.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_WIZARD_DB_PATH,
        help=f"Path to wizard DuckDB file (default: {DEFAULT_WIZARD_DB_PATH})",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=WIZARD_SCHEMA_SQL_PATH,
        help=f"Path to wizard schema SQL (default: {WIZARD_SCHEMA_SQL_PATH})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = initialize_wizard_schema(args.db_path, args.schema_path)
    print(f"Wizard schema initialized: {path}")


if __name__ == "__main__":
    main()
