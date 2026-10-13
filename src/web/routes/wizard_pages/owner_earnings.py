"""Owner Earnings wizard sub-page: context builder and POST handler.

Two tables, both on the stage *before* owner earnings (after opex → capex):

- ΔNWC build-up: the cash-flow working-capital change rows (CFO sign).
- Owner earnings: pretax income, one row per D&A item, ΔNWC — each D&A
  item and ΔNWC with its own maintenance-% input — and an Owner Earnings row
  of calculated cells.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.adjustments.types import owner_earnings as oe
from src.database.wizard_manager import WizardDatabaseManager
from src.models.table import CalculatedCellSpec, ColumnSpec, Table
from src.web.adjusted_statements import DEFAULT_EXCHANGE, load_adjusted
from src.web.settings import Settings

logger = logging.getLogger(__name__)

PCT_COLUMN = ColumnSpec(
    id="maintenance_pct", label="Maintenance %", kind="input", dtype="number"
)
PRETAX_ROW = "pretax"
NWC_ROW = "nwc"
OE_ROW = "owner_earnings"


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


def _cell(row: str, col: str) -> dict[str, Any]:
    return {"cell": [row, col]}


def _maintenance(row: str, period: str) -> dict[str, Any]:
    """``−pct%·value`` for ``row`` in ``period``."""
    return {
        "op": "mul",
        "args": [{"const": -0.01}, _cell(row, PCT_COLUMN.id), _cell(row, period)],
    }


def _oe_expr(period: str, da_ids: list[str]) -> dict[str, Any]:
    """``pretax + Σ D&A_i + ΔNWC − Σ pct_i%·D&A_i − pct_nwc%·ΔNWC``."""
    pct_rows = [*da_ids, NWC_ROW]
    return {
        "op": "add",
        "args": [
            _cell(PRETAX_ROW, period),
            *(_cell(row, period) for row in pct_rows),
            *(_maintenance(row, period) for row in pct_rows),
        ],
    }


def _oe_table(
    parts: pd.DataFrame, items: pd.DataFrame, periods: list[str], saved: dict
) -> Table:
    """Pretax, one row per D&A item, ΔNWC (each with a maintenance %), OE."""

    def record(row_id: str, label: str, values: dict, pct: object) -> dict:
        return {
            "row_id": row_id,
            "label": label,
            "level": 1 if row_id not in (PRETAX_ROW, NWC_ROW, OE_ROW) else 0,
            "is_total": row_id == OE_ROW,
            **{p: values.get(p) for p in periods},
            PCT_COLUMN.id: pct,
        }

    da_ids = items["row_id"].tolist()
    records = [
        record(PRETAX_ROW, "Pretax income (after adjustments)", parts["pretax"], None)
    ]
    records += [
        record(item["row_id"], item["label"], item, saved.get(item["row_id"]))
        for item in items.to_dict(orient="records")
    ]
    records += [
        record(
            NWC_ROW,
            "Change in NWC (CFO sign)",
            parts["nwc"],
            saved.get(oe.MAINTENANCE_NWC),
        ),
        record(OE_ROW, "Owner earnings", {}, None),
    ]
    return Table(
        pd.DataFrame(records),
        [*_period_specs(periods), PCT_COLUMN],
        {},
        row_id_col="row_id",
        level_col="level",
        calculated_cells=[
            CalculatedCellSpec(OE_ROW, p, _oe_expr(p, da_ids)) for p in periods
        ],
        no_input_cells=[(PRETAX_ROW, PCT_COLUMN.id), (OE_ROW, PCT_COLUMN.id)],
    )


def owner_earnings_context(ticker: str, settings: Settings) -> dict[str, object]:
    _, staged, specs = load_adjusted(ticker, settings.period, until=oe.TYPE_ID)
    parts = oe.components(staged)
    periods = settings.recent_periods(list(parts.index))
    items = oe.da_items(staged.cashflow)
    items = items[items[periods].notna().any(axis=1)]
    saved = next((dict(s.params) for s in specs if s.type_id == oe.TYPE_ID), {})
    return {
        "nwc_table": _nwc_table(oe.nwc_rows(staged.cashflow), periods).serialize(),
        "oe_table": _oe_table(parts, items, periods, saved).serialize(),
    }


def owner_earnings_post(ticker: str, body: dict[str, Any]) -> dict[str, Any]:
    """Save the maintenance % inputs as ``owner_earnings`` preferences."""
    rows = body.get("rows") or []
    if not rows:
        raise ValueError("rows is required")
    records = []
    for item in rows:
        row_id = str(item.get("id") or "")
        if not row_id or row_id in (PRETAX_ROW, OE_ROW):
            continue
        # D&A items are keyed by their statement row id; ΔNWC by a fixed key.
        key = oe.MAINTENANCE_NWC if row_id == NWC_ROW else row_id
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
