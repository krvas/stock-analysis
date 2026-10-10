"""Business Understanding wizard sub-pages: context builders."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.specs import describe
from src.ai_tools.runner import run_task
from src.ai_tools.tasks.one_line_answers import ONE_LINE_ANSWERS_TASK
from src.models.balance_leaves import balance_leaves
from src.models.statement import Statement, StatementView
from src.models.table import ColumnSpec, Table, period_column_specs
from src.web.adjusted_statements import load_for_basis
from src.web.settings import Settings

EQUITY_ROW_ID = "equity"
VALUE_COLUMN = ColumnSpec(
    id="value", label="Value", kind="static", dtype="number", format="financial"
)
CHANGE_COLUMN = ColumnSpec(
    id="change", label="Change", kind="static", dtype="number", format="financial"
)


def one_line_answers_context(ticker: str, settings: Settings) -> dict[str, Any]:
    result = run_task(ONE_LINE_ANSWERS_TASK, ticker)
    if result.answer is None:
        return {"ai_pending": True}
    fields = type(result.answer).model_fields
    return {
        "view": settings.view,
        "answers": [
            {"question": fields[name].description} | value.model_dump()
            for name, value in result.answer
        ],
    }


def _snapshot_items(balance: Statement, period: str) -> dict[str, list[dict[str, Any]]]:
    items: dict[str, list[dict[str, Any]]] = {"assets": [], "liabilities": []}
    equity = 0.0
    for leaf in balance_leaves(balance, period):
        value = leaf.display_value
        if leaf.is_equity:
            equity += value
        elif value > 0:
            items[leaf.side].append(
                {"row_id": leaf.row_id, "label": leaf.label, "value": value}
            )
    if equity > 0:
        items["liabilities"].append(
            {"row_id": EQUITY_ROW_ID, "label": "Equity", "value": equity}
        )
    return items


def _side_table(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    ranked = sorted(items, key=lambda item: item["value"], reverse=True)[:limit]
    frame = pd.DataFrame(ranked, columns=["row_id", "label", "value"])
    frame["level"] = 0
    frame["is_total"] = False
    return Table(frame, [VALUE_COLUMN], {}, row_id_col="row_id").serialize()


def balance_sheet_size_context(ticker: str, settings: Settings) -> dict[str, Any]:
    loaded = load_for_basis(ticker, "annual", settings.basis)
    balance = loaded.statements.balance
    context: dict[str, Any] = {
        "basis": settings.basis,
        "adjustments": describe(loaded.specs),
        "as_of": settings.period_at("current_period", balance.periods),
    }
    if context["as_of"] is None:
        return context
    items = _snapshot_items(balance, context["as_of"])
    return context | {
        "sides": {
            side: _side_table(rows, settings.items_per_side)
            for side, rows in items.items()
        }
    }


def fund_flow_table(
    balance: Statement, view: StatementView, current: str, previous: str
) -> Table:
    frame = balance.project(view, [current, previous])
    columns = period_column_specs(frame) + [CHANGE_COLUMN]
    frame[CHANGE_COLUMN.id] = frame[current] - frame[previous]
    return Table(
        frame,
        columns,
        {},
        row_id_col="row_id",
        level_col="level",
        is_total_col="is_total",
    )


def fund_flow_context(ticker: str, settings: Settings) -> dict[str, Any]:
    loaded = load_for_basis(ticker, settings.period, settings.basis)
    balance = loaded.statements.balance
    current = settings.period_at("current_period", balance.periods)
    previous = settings.period_at("previous_period", balance.periods)
    context: dict[str, Any] = {
        "basis": settings.basis,
        "adjustments": describe(loaded.specs),
    }
    if current is None or previous is None or current == previous:
        return context | {"not_enough_periods": True}
    table = fund_flow_table(balance, settings.view, current, previous)
    return context | {"fund_flow_table": table.serialize()}
