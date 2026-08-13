"""Serialize edgartools statement views for the HTML statement page."""

from __future__ import annotations

from typing import Any

import pandas as pd

_METADATA_COLUMNS = {
    "label",
    "concept",
    "standard_concept",
    "preferred_sign",
    "level",
    "is_total",
    "is_abstract",
}


def _period_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col not in _METADATA_COLUMNS]


def _serialize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    periods = _period_columns(df)
    rows: list[dict[str, Any]] = []
    for record in df.to_dict(orient="records"):
        row = {
            "label": record.get("label", ""),
            "level": int(record.get("level", 0) or 0),
            "is_total": bool(record.get("is_total", False)),
            "values": {
                period: None if pd.isna(record.get(period)) else record.get(period)
                for period in periods
            },
        }
        rows.append(row)
    return {"periods": periods, "rows": rows}


def _serialize_views(views: dict[str, pd.DataFrame]) -> dict[str, Any]:
    return {name: _serialize_dataframe(df) for name, df in views.items()}


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
