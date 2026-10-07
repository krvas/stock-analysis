"""Owner Earnings wizard sub-page: context builder and POST handler.

Two tables, both on the stage *before* owner earnings (after opex → capex):

- ΔNWC build-up: the cash-flow working-capital change rows (CFO sign).
- Owner earnings: pretax income, D&A, ΔNWC with a maintenance-% input on
  D&A and ΔNWC, and an Owner Earnings row of calculated cells
  (``pretax + D&A + ΔNWC − pct_da%·D&A − pct_nwc%·ΔNWC``).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.adjustments.types import owner_earnings as oe
from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import PeriodType
from src.models.table import CalculatedCellSpec, ColumnSpec, Table
from src.web.adjusted_statements import DEFAULT_EXCHANGE, load_adjusted

logger = logging.getLogger(__name__)

NUM_PERIODS = 5

PCT_COLUMN = ColumnSpec(
    id="maintenance_pct", label="Maintenance %", kind="input", dtype="number"
)
# Table row id → saved pref key (``base_concept``).
PCT_ROWS = {"da": oe.MAINTENANCE_DA, "nwc": oe.MAINTENANCE_NWC}


def _period_specs(periods: list[str]) -> list[ColumnSpec]:
    return [
        ColumnSpec(id=p, label=p, kind="static", dtype="number", format="financial")
        for p in periods
    ]


def _nwc_table(nwc: pd.DataFrame, periods: list[str]) -> Table:
    rows = nwc[["row_id", "label", *periods]].copy()
    rows = rows[rows[periods].notna().any(axis=1)]
    rows["level"] = 1
    rows["is_total"] = False
    total = {"row_id": "nwc_total", "label": "Change in NWC", "level": 0}
    total |= {p: pd.to_numeric(rows[p], errors="coerce").sum() for p in periods}
    total["is_total"] = True
    frame = pd.concat([rows, pd.DataFrame([total])], ignore_index=True)
    return Table(
        frame, _period_specs(periods), {}, row_id_col="row_id", level_col="level"
    )


def _oe_expr(period: str) -> dict[str, Any]:
    def cell(row: str, col: str) -> dict[str, Any]:
        return {"cell": [row, col]}

    def maintenance(row: str) -> dict[str, Any]:
        return {
            "op": "mul",
            "args": [{"const": -0.01}, cell(row, PCT_COLUMN.id), cell(row, period)],
        }

    return {
        "op": "add",
        "args": [
            cell("pretax", period),
            cell("da", period),
            cell("nwc", period),
            maintenance("da"),
            maintenance("nwc"),
        ],
    }


def _oe_table(parts: pd.DataFrame, periods: list[str], saved: dict) -> Table:
    labels = {
        "pretax": "Pretax income (after adjustments)",
        "da": "Depreciation & amortization",
        "nwc": "Change in NWC (CFO sign)",
        "owner_earnings": "Owner earnings",
    }
    records = []
    for row_id, label in labels.items():
        record: dict[str, Any] = {
            "row_id": row_id,
            "label": label,
            "level": 0,
            "is_total": row_id == "owner_earnings",
        }
        for p in periods:
            record[p] = parts.at[p, row_id] if row_id in parts.columns else None
        record[PCT_COLUMN.id] = (
            saved.get(PCT_ROWS[row_id]) if row_id in PCT_ROWS else None
        )
        records.append(record)
    return Table(
        pd.DataFrame(records),
        [*_period_specs(periods), PCT_COLUMN],
        {},
        row_id_col="row_id",
        level_col="level",
        calculated_cells=[
            CalculatedCellSpec("owner_earnings", p, _oe_expr(p)) for p in periods
        ],
        no_input_cells=[("pretax", PCT_COLUMN.id), ("owner_earnings", PCT_COLUMN.id)],
    )


def owner_earnings_context(ticker: str, period: PeriodType) -> dict[str, object]:
    _, staged, specs = load_adjusted(ticker, period, until=oe.TYPE_ID)
    parts = oe.components(staged)
    periods = [p for p in parts.index[:NUM_PERIODS]]
    saved = next((dict(s.params) for s in specs if s.type_id == oe.TYPE_ID), {})
    return {
        "nwc_table": _nwc_table(oe.nwc_rows(staged.cashflow), periods).serialize(),
        "oe_table": _oe_table(parts, periods, saved).serialize(),
    }


def owner_earnings_post(ticker: str, body: dict[str, Any]) -> dict[str, Any]:
    """Save the maintenance % inputs as ``owner_earnings`` preferences."""
    rows = body.get("rows") or []
    if not rows:
        raise ValueError("rows is required")
    records = []
    for item in rows:
        key = PCT_ROWS.get(item.get("id"))
        if key is None:
            continue
        value = (item.get("cells") or {}).get(PCT_COLUMN.id)
        if value is None or value == "":
            value = 0.0
        try:
            pct = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a number") from exc
        if not 0 <= pct <= 100:
            raise ValueError(f"{key} must be between 0 and 100")
        records.append(
            {
                "ticker": ticker,
                "exchange": DEFAULT_EXCHANGE,
                "statement": "CF",
                "adjustment_type": oe.TYPE_ID,
                "base_concept": key,
                "base_concept_statement": "CF",
                "value": pct,
            }
        )
    if not records:
        raise ValueError("no maintenance % rows in body")
    with WizardDatabaseManager() as db:
        result = db.upsert_adjustment_preferences(pd.DataFrame(records))
    logger.info(
        "Owner-earnings POST for %s wrote %d row(s)", ticker, result.rows_written
    )
    return {"ok": True, "rows_written": result.rows_written}
