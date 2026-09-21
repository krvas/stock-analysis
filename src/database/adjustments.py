"""Public API for wizard adjustment preferences (read/upsert only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import DEFAULT_WIZARD_DB_PATH
from src.database.manager import UpsertResult
from src.database.wizard_manager import WizardDatabaseManager


def upsert_adjustment_preferences(
    df: pd.DataFrame,
    *,
    db_path: Path | str | None = None,
) -> UpsertResult:
    """Persist adjustment preference rows to the wizard database."""
    with WizardDatabaseManager(db_path or DEFAULT_WIZARD_DB_PATH) as db:
        return db.upsert_adjustment_preferences(df)


def read_adjustment_preferences(
    ticker: str,
    exchange: str,
    *,
    db_path: Path | str | None = None,
) -> pd.DataFrame:
    """Load stored adjustment preferences for a company."""
    with WizardDatabaseManager(db_path or DEFAULT_WIZARD_DB_PATH, read_only=True) as db:
        return db.read_adjustment_preferences(ticker, exchange)
