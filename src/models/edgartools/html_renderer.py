"""Render edgartools statement views as a self-contained HTML file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROCESSED_DATA_DIR

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "statement_view.html"
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


def render_statement_html(
    views: dict[str, pd.DataFrame],
    *,
    ticker: str,
    statement_type: str,
    period: str,
    output_path: Path | None = None,
) -> Path:
    """Inject view data into the static template and write a standalone HTML file."""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = {
        "ticker": ticker,
        "statement_type": statement_type,
        "period": period,
        "views": _serialize_views(views),
    }
    rendered = template.replace("__STATEMENT_DATA__", json.dumps(payload))
    destination = output_path or (
        PROCESSED_DATA_DIR / f"{ticker.lower()}_{statement_type}_{period}.html"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    return destination.resolve()
