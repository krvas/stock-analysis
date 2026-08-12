"""Central configuration: paths, retention, and database location."""

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

# Schema SQL file
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "database" / "schema.sql"

# Historical data retention target (years)
HISTORY_YEARS = 10

# SEC EDGAR identity (contact email loaded from SEC_CONTACT_EMAIL in .env)
SEC_APP_IDENTITY = "ScreenerApp/1.0"

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
