"""POST handlers for Adjustment wizard sub-pages."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter

from src.database.wizard_manager import WizardDatabaseManager

logger = logging.getLogger(__name__)


def _validate_opex_to_capex_body(
    body: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    exchange = body.get("exchange")
    if not exchange or not str(exchange).strip():
        raise ValueError("exchange is required")

    columns = body.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("columns is required")
    column_ids = {
        col.get("id") for col in columns if isinstance(col, dict)
    }
    missing_columns = {"capitalize", "years"} - column_ids
    if missing_columns:
        raise ValueError(
            f"columns is missing required id(s): {sorted(missing_columns)}"
        )

    raw_rows = body.get("rows")
    if raw_rows is None:
        raise ValueError("rows is required")
    if not isinstance(raw_rows, list):
        raise ValueError("rows must be a list")

    validated_rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            raise ValueError(f"rows[{index}] must be an object")

        cells = item.get("cells")
        if not isinstance(cells, dict):
            raise ValueError(f"rows[{index}].cells must be an object")

        if not cells.get("capitalize"):
            continue

        base_concept = item.get("id")
        if not base_concept or not str(base_concept).strip():
            raise ValueError(f"rows[{index}].id is required when capitalize is true")

        years = cells.get("years")
        if years is None:
            raise ValueError(f"rows[{index}].cells.years is required when capitalize is true")

        validated_rows.append(
            {
                "base_concept": str(base_concept).strip(),
                "years": float(years),
                "consolidated_ids": cells.get("consolidated_ids"),
            }
        )

    return str(exchange).strip(), validated_rows


def opex_to_capex_post(ticker: str, body: dict[str, Any]) -> dict[str, Any]:
    """Persist capitalized opex line items to ``adjustment_preferences``."""
    exchange, raw_rows = _validate_opex_to_capex_body(body)

    records: list[dict[str, object]] = []
    for item in raw_rows:
        consolidated_ids = item.get("consolidated_ids")
        records.append(
            {
                "ticker": ticker,
                "exchange": str(exchange).strip(),
                "statement": "BS",
                "adjustment_type": "opex_to_capex",
                "base_concept": item["base_concept"],
                "base_concept_statement":  "PL",
                "value": item["years"],
                "consolidated_ids": (
                    None
                    if consolidated_ids is None
                    else str(consolidated_ids).strip() or None
                ),
            }
        )

    if not records:
        return {"ok": True, "rows_written": 0}

    df = pd.DataFrame(records)
    with WizardDatabaseManager() as db:
        result = db.upsert_adjustment_preferences(df)

    logger.info(
        "Opex-to-capex POST for %s wrote %d row(s)",
        ticker,
        result.rows_written,
    )
    return {"ok": True, "rows_written": result.rows_written}


