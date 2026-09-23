"""DuckDB connection management and schema initialization."""

from src.database.adjustments import (
    read_adjustment_preferences,
    upsert_adjustment_preferences,
)
from src.database.init_schema import initialize_schema
from src.database.init_wizard_schema import initialize_wizard_schema
from src.database.manager import BaseDatabaseManager, DatabaseManager, UpsertResult
from src.database.wizard_manager import WizardDatabaseManager

__all__ = [
    "BaseDatabaseManager",
    "DatabaseManager",
    "UpsertResult",
    "WizardDatabaseManager",
    "initialize_schema",
    "initialize_wizard_schema",
    "read_adjustment_preferences",
    "upsert_adjustment_preferences",
]
