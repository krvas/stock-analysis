"""Initialize DuckDB schema from schema.sql.

Run directly:
    python -m src.database.init_schema

Or import and call ``initialize_schema(db_path)``.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.config import DEFAULT_DB_PATH, SCHEMA_SQL_PATH
from src.database.manager import DatabaseManager

logger = logging.getLogger(__name__)


def initialize_schema(db_path: Path | None = None, schema_path: Path | None = None) -> Path:
    """Create database file and apply all CREATE TABLE / VIEW statements.

    Args:
        db_path: Target DuckDB file. Defaults to ``data/duckdb/indian_stocks.duckdb``.
        schema_path: SQL file with DDL. Defaults to ``src/database/schema.sql``.

    Returns:
        Resolved path to the initialized database file.
    """
    db_path = (db_path or DEFAULT_DB_PATH).resolve()
    schema_path = (schema_path or SCHEMA_SQL_PATH).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    logger.info("Initializing DuckDB at %s", db_path)
    with DatabaseManager(db_path, auto_connect=True) as db:
        db.initialize_schema(schema_path)
        logger.info("Created tables: %s", db.list_tables())

    return db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize DuckDB schema for Indian stocks.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=SCHEMA_SQL_PATH,
        help=f"Path to schema SQL file (default: {SCHEMA_SQL_PATH})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = initialize_schema(args.db_path, args.schema_path)
    print(f"Schema initialized: {path}")


if __name__ == "__main__":
    main()
