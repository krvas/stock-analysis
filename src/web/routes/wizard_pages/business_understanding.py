"""Business Understanding wizard sub-pages: context builders."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.ai_tools.runner import run_task
from src.ai_tools.tasks.one_line_answers import ONE_LINE_ANSWERS_TASK
from src.api.edgartools.source import load_statement_set
from src.api.edgartools.standard_terms import (
    BALANCE_ASSETS_ROOT,
    BALANCE_LIABILITIES_EQUITY_ROOT,
    EQUITY_PARENTS,
)
from src.models.table import ColumnSpec, Table

EQUITY_ROW_ID = "equity"
MAX_ITEMS_PER_SIDE = 10
VALUE_COLUMN = ColumnSpec(
    id="value", label="Value", kind="static", dtype="number", format="financial"
)


def one_line_answers_context(ticker: str, period: str) -> dict[str, Any]:
    """Each question (field description) with its AI answer, in field order."""
    result = run_task(ONE_LINE_ANSWERS_TASK, ticker)
    if result.answer is None:
        return {"ai_pending": True}
    fields = type(result.answer).model_fields
    return {
        "answers": [
            {"question": fields[name].description} | value.model_dump()
            for name, value in result.answer
        ]
    }


def _snapshot_items(balance: Any, period: str) -> dict[str, list[dict[str, Any]]]:
    """Balance-sheet leaves of ``period`` split by calc root (assets / liabilities).

    Equity leaves are netted into one item; other non-positive leaves drop.
    """
    edges = balance.calc_edges
    edges = edges[edges["period"] == period]
    parent = dict(zip(edges["concept"], edges["parent_concept"], strict=True))
    parents = set(parent.values())
    items: dict[str, list[dict[str, Any]]] = {"assets": [], "liabilities": []}
    equity = 0.0
    for row in balance.project("summary", [period]).to_dict("records"):
        value, concept = row[period], row["concept"]
        if concept in parents or not isinstance(value, float) or math.isnan(value):
            continue
        chain, node = [concept], concept
        while node in parent and parent[node] not in chain:
            node = parent[node]
            chain.append(node)
        root = chain[-1]
        if root == BALANCE_ASSETS_ROOT:
            side = "assets"
        elif root == BALANCE_LIABILITIES_EQUITY_ROOT:
            side = "liabilities"
        else:
            continue
        if any(c in EQUITY_PARENTS for c in chain):
            equity += value
        elif value > 0:
            items[side].append(
                {"row_id": row["row_id"], "label": row["label"], "value": value}
            )
    if equity > 0:
        items["liabilities"].append(
            {"row_id": EQUITY_ROW_ID, "label": "Equity", "value": equity}
        )
    return items


def _side_table(items: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(items, key=lambda item: item["value"], reverse=True)
    ranked = ranked[:MAX_ITEMS_PER_SIDE]
    frame = pd.DataFrame(ranked, columns=["row_id", "label", "value"])
    frame["level"] = 0
    frame["is_total"] = False
    return Table(frame, [VALUE_COLUMN], {}, row_id_col="row_id").serialize()


def balance_sheet_size_context(ticker: str, period: str) -> dict[str, Any]:
    """Every annual balance sheet as two ranked Tables of at most 10 items each.

    ``period`` is ignored: the snapshot is annual-only. The template picks the
    period and the page script picks how many of the ranked items to draw.
    """
    balance = load_statement_set(ticker, "annual").balance
    periods = sorted(balance.periods, reverse=True)
    snapshots = {}
    for p in periods:
        items = _snapshot_items(balance, p)
        snapshots[p] = {side: _side_table(rows) for side, rows in items.items()}
    return {
        "periods": periods,
        "snapshots": snapshots,
        "max_items_per_side": MAX_ITEMS_PER_SIDE,
    }
