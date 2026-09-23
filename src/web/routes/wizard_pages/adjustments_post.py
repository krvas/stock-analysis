"""POST handlers for Adjustment wizard sub-pages."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.database.wizard_manager import WizardDatabaseManager
from src.models.table import Table, TableSerializationError
from src.web.routes.wizard_pages.adjustments_context import OPEX_TO_CAPEX_INPUT_COLUMNS

logger = logging.getLogger(__name__)


def _validate_opex_to_capex_body(
    body: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    exchange = body.get("exchange")
    if not exchange or not str(exchange).strip():
        raise ValueError("exchange is required")

    raw_rows = body.get("rows")
    if raw_rows is None:
        raise ValueError("rows is required")

    try:
        table = Table.from_rows(raw_rows, OPEX_TO_CAPEX_INPUT_COLUMNS)
    except TableSerializationError as exc:
        raise ValueError(str(exc)) from exc

    validated_rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_rows):
        row_id = item["id"]

        if not table.get_cell(row_id, "capitalize"):
            continue

        if not row_id or not str(row_id).strip():
            raise ValueError(f"rows[{index}].id is required when capitalize is true")
        base_concept = str(row_id).strip()

        years = table.get_cell(row_id, "years")
        if years is None:
            raise ValueError(f"rows[{index}].cells.years is required when capitalize is true")

        cells = item.get("cells") or {}
        validated_rows.append(
            {
                "base_concept": base_concept,
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


