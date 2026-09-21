"""Central configuration: paths, retention, and database location."""

import os
from pathlib import Path

# Project root is two levels above src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DUCKDB_DIR = DATA_DIR / "duckdb"

# Default DuckDB file path
DEFAULT_DB_PATH = DUCKDB_DIR / "indian_stocks.duckdb"
DEFAULT_WIZARD_DB_PATH = DUCKDB_DIR / "wizard.duckdb"

# Schema SQL files
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "database" / "schema.sql"
WIZARD_SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "database" / "wizard.sql"

# Historical data retention target (years)
HISTORY_YEARS = 10

# edgartools local filing cache (LRU by company)
EDGARTOOLS_CACHE_DIR = DATA_DIR / "edgartools_cache"
# Keep this many most recently viewed companies; older ones are deleted.
# Override with EDGARTOOLS_COMPANY_CACHE_SIZE env var when storage is tight.
EDGARTOOLS_COMPANY_CACHE_SIZE = max(
    1,
    int(os.environ.get("EDGARTOOLS_COMPANY_CACHE_SIZE", "10")),
)
# Refetch cached statements when the latest stored filing date is older than these.
EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS = max(
    1,
    int(os.environ.get("EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS", "3")),
)
EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS = max(
    1,
    int(os.environ.get("EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS", "12")),
)

# Logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "platform.log"

# Parquet partitioning hints (used by ingestion modules)
RAW_SUBDIRS = {
    "companies": RAW_DATA_DIR / "companies",
    "prices": RAW_DATA_DIR / "prices",
    "financials": RAW_DATA_DIR / "financials",
    "balance_sheets": RAW_DATA_DIR / "balance_sheets",
    "cash_flows": RAW_DATA_DIR / "cash_flows",
    "corporate_actions": RAW_DATA_DIR / "corporate_actions",
}
