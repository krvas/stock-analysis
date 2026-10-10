from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.adjustments.types import assets_in_use as aiu
from src.config import MAX_PERIODS_BY_PERIOD
from src.database.wizard_manager import WizardDatabaseManager
from src.models.balance_leaves import Side, balance_leaves
from src.models.statement import Statement
from src.models.table import (
    CalculatedCellSpec,
    ColumnSpec,
    Table,
    TableSerializationError,
    period_column_specs,
)
from src.web.adjusted_statements import DEFAULT_EXCHANGE, load_adjusted
from src.web.settings import Settings

logger = logging.getLogger(__name__)

PCT_COLUMN = ColumnSpec(id="pct_in_use", label="% in use", kind="input", dtype="number")
NET_OUT_COLUMN = ColumnSpec(
    id="net_out", label="Net out", kind="input", dtype="boolean"
)
INPUT_COLUMNS = [PCT_COLUMN, NET_OUT_COLUMN]
TOTAL_ROW = "total_assets"
GROSS_ROW = "gross_assets_in_use"
NET_ROW = "net_assets_in_use"


def side_rows(balance: Statement, periods: list[str]) -> dict[Side, pd.DataFrame]:
    found: dict[str, dict[str, Any]] = {}
    for period in periods:
        for leaf in balance_leaves(balance, period):
            if leaf.is_equity:
                continue
            row = found.setdefault(
                leaf.row_id,
                {"row_id": leaf.row_id, "label": leaf.label, "side": leaf.side},
            )
            row[period] = leaf.contribution
    position = {row_id: i for i, row_id in enumerate(balance.frame["row_id"])}
    ordered = sorted(found.values(), key=lambda row: position[row["row_id"]])
    frame = pd.DataFrame(ordered, columns=["row_id", "label", "side", *periods])
    return {
        side: frame[frame["side"] == side].drop(columns="side").reset_index(drop=True)
        for side in ("assets", "liabilities")
    }


def _staged_balance_and_saved(ticker: str) -> tuple[Statement, dict[str, float]]:
    _, staged, specs = load_adjusted(ticker, "annual", until=aiu.TYPE_ID)
    saved = next((dict(s.params) for s in specs if s.type_id == aiu.TYPE_ID), {})
    return staged.balance, saved


def _cell(row: str, col: str) -> dict[str, Any]:
    return {"cell": [row, col]}


def _mul(*args: dict[str, Any]) -> dict[str, Any]:
    return {"op": "mul", "args": list(args)}


def _gross_terms(period: str, asset_ids: list[str]) -> list[dict[str, Any]]:
    terms = [_cell(TOTAL_ROW, period)]
    for row in asset_ids:
        terms.append(
            _mul({"const": 0.01}, _cell(row, PCT_COLUMN.id), _cell(row, period))
        )
        terms.append(_mul({"const": -1}, _cell(row, period)))
    return terms


def _net_terms(period: str, liability_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _mul({"const": -1}, _cell(row, NET_OUT_COLUMN.id), _cell(row, period))
        for row in liability_ids
    ]


def _table(
    total: dict[str, float],
    sides: dict[Side, pd.DataFrame],
    periods: list[str],
    saved: dict[str, float],
) -> Table:
    assets, liabilities = sides["assets"], sides["liabilities"]
    asset_ids = assets["row_id"].tolist()
    liability_ids = liabilities["row_id"].tolist()

    def structural(row_id: str, label: str, values: dict) -> pd.DataFrame:
        row = {"row_id": row_id, "label": label, "level": 0, "is_total": True}
        return pd.DataFrame([row | {p: values.get(p) for p in periods}])

    frame = pd.concat(
        [
            structural(TOTAL_ROW, "Total assets", total),
            assets.assign(level=1, is_total=False),
            structural(GROSS_ROW, "Gross assets in use", {}),
            liabilities.assign(level=1, is_total=False),
            structural(NET_ROW, "Net assets in use", {}),
        ],
        ignore_index=True,
    )
    structural_ids = (TOTAL_ROW, GROSS_ROW, NET_ROW)
    calculated = []
    for period in periods:
        gross = _gross_terms(period, asset_ids)
        net = gross + _net_terms(period, liability_ids)
        calculated += [
            CalculatedCellSpec(GROSS_ROW, period, {"op": "add", "args": gross}),
            CalculatedCellSpec(NET_ROW, period, {"op": "add", "args": net}),
        ]
    table = Table(
        frame,
        period_column_specs(frame) + INPUT_COLUMNS,
        {},
        row_id_col="row_id",
        level_col="level",
        calculated_cells=calculated,
        no_input_cells=[
            *((row, NET_OUT_COLUMN.id) for row in asset_ids),
            *((row, PCT_COLUMN.id) for row in liability_ids),
            *((row, col.id) for row in structural_ids for col in INPUT_COLUMNS),
        ],
    )
    for row in asset_ids:
        table.set_cell(PCT_COLUMN.id, row, saved.get(row, 100.0))
    for row in liability_ids:
        table.set_cell(NET_OUT_COLUMN.id, row, saved.get(row) == aiu.NETTED)
    return table


def assets_in_use_context(ticker: str, settings: Settings) -> dict[str, object]:
    balance, saved = _staged_balance_and_saved(ticker)
    count = min(settings.num_periods, MAX_PERIODS_BY_PERIOD["annual"])
    periods = balance.periods[:count]
    _, total = aiu.total_assets(balance)
    table = _table(total, side_rows(balance, periods), periods, saved)
    return {"aiu_table": table.serialize()}


def _pct(value: object, label: str) -> float:
    if value is None or value == "" or isinstance(value, bool):
        raise ValueError(f"{label}: % in use is required")
    try:
        pct = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: % in use must be a number") from exc
    if not 0 <= pct <= 100:
        raise ValueError(f"{label}: % in use must be between 0 and 100")
    return pct


def _record(ticker: str, row_id: str, value: float) -> dict[str, object]:
    return {
        "ticker": ticker,
        "exchange": DEFAULT_EXCHANGE,
        "statement": "BS",
        "adjustment_type": aiu.TYPE_ID,
        "base_concept": row_id,
        "base_concept_statement": "BS",
        "value": value,
    }


def assets_in_use_post(ticker: str, body: dict[str, Any]) -> dict[str, Any]:
    rows = body.get("rows")
    if rows is None:
        raise ValueError("rows is required")
    try:
        posted = Table.from_rows(rows, INPUT_COLUMNS)
    except TableSerializationError as exc:
        raise ValueError(str(exc)) from exc
    balance, _ = _staged_balance_and_saved(ticker)
    sides = side_rows(balance, balance.periods)
    assets = dict(zip(sides["assets"]["row_id"], sides["assets"]["label"], strict=True))
    liabilities = set(sides["liabilities"]["row_id"])

    records: list[dict[str, object]] = []
    to_delete: list[str] = []
    for item in rows:
        row_id = str(item["id"])
        if row_id in assets:
            pct = _pct(posted.get_cell(row_id, PCT_COLUMN.id), assets[row_id])
            records.append(_record(ticker, row_id, pct))
        elif row_id in liabilities:
            if posted.get_cell(row_id, NET_OUT_COLUMN.id) is True:
                records.append(_record(ticker, row_id, aiu.NETTED))
            else:
                to_delete.append(row_id)

    rows_written = rows_deleted = 0
    if records or to_delete:
        with WizardDatabaseManager() as db:
            if records:
                written = db.upsert_adjustment_preferences(pd.DataFrame(records))
                rows_written = written.rows_written
            if to_delete:
                keys = [(ticker, DEFAULT_EXCHANGE, aiu.TYPE_ID, r) for r in to_delete]
                rows_deleted = db.delete_adjustment_preferences(keys).rows_deleted
    logger.info(
        "Assets-in-use POST for %s wrote %d row(s), deleted %d row(s)",
        ticker,
        rows_written,
        rows_deleted,
    )
    return {"ok": True, "rows_written": rows_written, "rows_deleted": rows_deleted}
