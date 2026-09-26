"""POST handlers for Adjustment wizard sub-pages."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.database.wizard_manager import WizardDatabaseManager
from src.models.table import Table, TableSerializationError
from src.web.routes.wizard_pages.adjustments_context import (
    DEFAULT_EXCHANGE,
    OPEX_TO_CAPEX_ADJUSTMENT_TYPE,
    OPEX_TO_CAPEX_INPUT_COLUMNS,
)

logger = logging.getLogger(__name__)


def _validate_opex_to_capex_body(
    body: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate the opex-to-capex save payload.

    Returns ``(rows_to_upsert, base_concepts_to_delete)``. Every posted row
    is either checked (upsert) or unchecked (delete) -- there is no third
    case. An unchecked row with a missing/blank id is skipped from the
    delete list rather than raising, since there is no meaningful key to
    delete without an id.
    """
    raw_rows = body.get("rows")
    if raw_rows is None:
        raise ValueError("rows is required")

    try:
        table = Table.from_rows(raw_rows, OPEX_TO_CAPEX_INPUT_COLUMNS)
    except TableSerializationError as exc:
        raise ValueError(str(exc)) from exc

    validated_rows: list[dict[str, Any]] = []
    base_concepts_to_delete: list[str] = []
    for index, item in enumerate(raw_rows):
        row_id = item["id"]

        if not table.get_cell(row_id, "capitalize"):
            if row_id and str(row_id).strip():
                base_concepts_to_delete.append(str(row_id).strip())
            continue

        if not row_id or not str(row_id).strip():
            raise ValueError(f"rows[{index}].id is required when capitalize is true")
        base_concept = str(row_id).strip()

        years = table.get_cell(row_id, "years")
        if years is None:
            raise ValueError(f"rows[{index}].cells.years is required when capitalize is true")

        validated_rows.append(
            {
                "base_concept": base_concept,
                "years": float(years),
            }
        )

    return validated_rows, base_concepts_to_delete


def opex_to_capex_post(ticker: str, body: dict[str, Any]) -> dict[str, Any]:
    """Persist capitalized opex line items to ``adjustment_preferences``.

    Unchecked rows have their previously-saved preference (if any) deleted.
    """
    raw_rows, base_concepts_to_delete = _validate_opex_to_capex_body(body)

    records: list[dict[str, object]] = []
    for item in raw_rows:
        records.append(
            {
                "ticker": ticker,
                "exchange": DEFAULT_EXCHANGE,
                "statement": "BS",
                "adjustment_type": OPEX_TO_CAPEX_ADJUSTMENT_TYPE,
                "base_concept": item["base_concept"],
                "base_concept_statement": "PL",
                "value": item["years"],
            }
        )

    if not records and not base_concepts_to_delete:
        return {"ok": True, "rows_written": 0, "rows_deleted": 0}

    rows_written = 0
    rows_deleted = 0
    with WizardDatabaseManager() as db:
        if records:
            df = pd.DataFrame(records)
            result = db.upsert_adjustment_preferences(df)
            rows_written = result.rows_written

        if base_concepts_to_delete:
            delete_keys = [
                (ticker, DEFAULT_EXCHANGE, OPEX_TO_CAPEX_ADJUSTMENT_TYPE, base_concept)
                for base_concept in base_concepts_to_delete
            ]
            delete_result = db.delete_adjustment_preferences(delete_keys)
            rows_deleted = delete_result.rows_deleted

    logger.info(
        "Opex-to-capex POST for %s wrote %d row(s), deleted %d row(s)",
        ticker,
        rows_written,
        rows_deleted,
    )
    return {"ok": True, "rows_written": rows_written, "rows_deleted": rows_deleted}


