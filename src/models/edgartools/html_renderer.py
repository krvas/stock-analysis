"""Serialize edgartools statement views for the HTML statement page."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.models.table import statement_table_from_dataframe


def _serialize_views(views: dict[str, pd.DataFrame]) -> dict[str, Any]:
    return {name: statement_table_from_dataframe(df).serialize() for name, df in views.items()}


def build_statement_payload(
    all_views: dict[str, dict[str, pd.DataFrame]],
    *,
    ticker: str,
    period: str,
) -> dict[str, Any]:
    """Build the JSON payload embedded in the statement Jinja template."""
    return {
        "ticker": ticker,
        "period": period,
        "statements": {
            statement_type: _serialize_views(views)
            for statement_type, views in all_views.items()
        },
    }
