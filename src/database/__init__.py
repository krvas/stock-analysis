"""DuckDB connection management and schema initialization."""

from src.database.init_schema import initialize_schema
from src.database.manager import DatabaseManager, UpsertResult

__all__ = ["DatabaseManager", "UpsertResult", "initialize_schema"]
