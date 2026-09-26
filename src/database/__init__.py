"""DuckDB connection management and schema initialization."""

from src.database.init_schema import initialize_schema
from src.database.init_wizard_schema import initialize_wizard_schema
from src.database.manager import BaseDatabaseManager, DatabaseManager, UpsertResult
from src.database.wizard_manager import WizardDatabaseManager

__all__ = [
    "BaseDatabaseManager",
    "DatabaseManager",
    "WizardDatabaseManager",
    "UpsertResult",
    "initialize_schema",
    "initialize_wizard_schema",
]
