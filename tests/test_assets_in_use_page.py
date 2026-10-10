"""Assets in Use sub-page: the table the builder returns and what POST saves."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.types.assets_in_use import GROSS_CONCEPT, NET_CONCEPT, TYPE_ID
from src.web import adjusted_statements
from src.web.routes.wizard_pages import assets_in_use as page
from src.web.settings import resolve
from src.web.wizard_registry import get_subpage
from tests.statement_fixtures import P1, P2, P3
from tests.test_assets_in_use import _statements

SAVED = {"Construction": 0.0, "Allowance": 50.0, "Payables": 1.0}
ASSETS = [
    "Cash",
    "Receivables",
    "Allowance",
    "Construction",
    "Split",
    "SplitA",
    "SplitB",
]
LIABILITIES = ["Payables", "Advances", "Debt"]


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    periods: list[str] = []

    def load(ticker: str, period: str):
        periods.append(period)
        return _statements()

    monkeypatch.setattr(adjusted_statements, "load_statement_set", load)
    monkeypatch.setattr(
        adjusted_statements, "load_specs", lambda _: [AdjustmentSpec(TYPE_ID, SAVED)]
    )
    return periods


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    calls = SimpleNamespace(upserted=[], deleted=[])

    class FakeDb:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def __enter__(self) -> FakeDb:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def upsert_adjustment_preferences(self, df: pd.DataFrame) -> SimpleNamespace:
            calls.upserted.extend(df.to_dict("records"))
            return SimpleNamespace(rows_written=len(df))

        def delete_adjustment_preferences(self, keys: list) -> SimpleNamespace:
            calls.deleted.extend(keys)
            return SimpleNamespace(rows_deleted=len(keys))

    monkeypatch.setattr(page, "WizardDatabaseManager", FakeDb)
    return calls


def _context(**values: object) -> dict:
    decl = get_subpage("adjustments", "assets-in-use").settings
    return page.assets_in_use_context("AAPL", resolve(json.dumps(values), decl))[
        "aiu_table"
    ]


def _rows(table: dict) -> dict[str, dict]:
    return {row["id"]: row for row in table["rows"]}


def _evaluate(expr: dict, cells: dict[str, dict]) -> float:
    """What the browser computes: booleans count as 1/0, blanks as 0."""
    if "cell" in expr:
        row, col = expr["cell"]
        value = cells[row].get(col)
        return 0.0 if value is None else float(value)
    if "const" in expr:
        return expr["const"]
    values = [_evaluate(arg, cells) for arg in expr["args"]]
    if expr["op"] == "add":
        return sum(values)
    product = 1.0
    for value in values:
        product *= value
    return product


def test_rows_are_total_assets_leaves_gross_liability_leaves_net(loads) -> None:
    table = _context()
    ids = [row["id"] for row in table["rows"]]
    assert ids == [
        page.TOTAL_ROW,
        *ASSETS,
        page.GROSS_ROW,
        *LIABILITIES,
        page.NET_ROW,
    ]
    rows = _rows(table)
    assert rows[page.TOTAL_ROW]["cells"][P1] == 175.0
    assert rows["Allowance"]["cells"][P1] == -5.0
    assert (rows["Split"]["cells"][P2], rows["SplitA"]["cells"][P2]) == (None, 12.0)
    assert loads == ["annual"]


def test_columns_follow_num_periods_on_annual_even_when_quarterly_is_set(
    loads,
) -> None:
    def columns(table: dict) -> list[str]:
        return [c["id"] for c in table["columns"]]

    assert columns(_context(period="quarterly")) == [
        P1,
        P2,
        P3,
        "pct_in_use",
        "net_out",
    ]
    assert columns(_context(num_periods=2)) == [P1, P2, "pct_in_use", "net_out"]
    assert loads == ["annual", "annual"]


def test_inputs_only_where_they_apply_and_prefilled_from_saved(loads) -> None:
    table = _context()
    missing = {tuple(cell) for cell in table["no_input_cells"]}
    structural = (page.TOTAL_ROW, page.GROSS_ROW, page.NET_ROW)
    assert missing == {
        *((row, "net_out") for row in ASSETS),
        *((row, "pct_in_use") for row in LIABILITIES),
        *((row, col) for row in structural for col in ("pct_in_use", "net_out")),
    }
    rows = _rows(table)
    assert {row: rows[row]["cells"]["pct_in_use"] for row in ASSETS} == {
        "Cash": 100.0,
        "Receivables": 100.0,
        "Allowance": 50.0,
        "Construction": 0.0,
        "Split": 100.0,
        "SplitA": 100.0,
        "SplitB": 100.0,
    }
    assert {row: rows[row]["cells"]["net_out"] for row in LIABILITIES} == {
        "Payables": True,
        "Advances": False,
        "Debt": False,
    }


def test_live_gross_and_net_match_the_adjustment_on_saved_choices(loads) -> None:
    table = _context()
    cells = {row["id"]: row["cells"] for row in table["rows"]}
    live = {
        (spec["row_id"], spec["col_id"]): _evaluate(spec["expr"], cells)
        for spec in table["calculated_cells"]
    }
    adjusted = apply_adjustments(_statements(), [AdjustmentSpec(TYPE_ID, SAVED)])
    frame = adjusted.balance.frame.set_index("concept")
    for period in (P1, P2):
        assert live[(page.GROSS_ROW, period)] == frame.at[GROSS_CONCEPT, period]
        assert live[(page.NET_ROW, period)] == frame.at[NET_CONCEPT, period]
    assert live[(page.GROSS_ROW, P1)] == 175.0 - 50.0 + 2.5
    assert live[(page.NET_ROW, P1)] == 175.0 - 50.0 + 2.5 - 30.0


def _post(rows: list[dict]) -> dict:
    return page.assets_in_use_post("AAPL", {"rows": rows})


def test_post_saves_pcts_and_netting_and_skips_other_rows(loads, db) -> None:
    result = _post(
        [
            {"id": page.TOTAL_ROW, "cells": {}},
            {"id": "Cash", "cells": {"pct_in_use": 100}},
            {"id": "Construction", "cells": {"pct_in_use": "25"}},
            {"id": page.GROSS_ROW, "cells": {}},
            {"id": "Payables", "cells": {"net_out": True}},
            {"id": "Advances", "cells": {"net_out": False}},
            {"id": "Common", "cells": {"net_out": True}},
            {"id": page.NET_ROW, "cells": {}},
        ]
    )
    assert result == {"ok": True, "rows_written": 3, "rows_deleted": 1}
    assert [
        (r["base_concept"], r["value"], r["adjustment_type"], r["statement"])
        for r in db.upserted
    ] == [
        ("Cash", 100.0, TYPE_ID, "BS"),
        ("Construction", 25.0, TYPE_ID, "BS"),
        ("Payables", 1.0, TYPE_ID, "BS"),
    ]
    assert db.deleted == [("AAPL", "NASDAQ", TYPE_ID, "Advances")]


@pytest.mark.parametrize("pct", [None, "", 101, -1, "abc"])
def test_post_rejects_a_missing_or_out_of_range_pct_naming_the_line(
    loads, db, pct: object
) -> None:
    with pytest.raises(ValueError, match="Construction in progress"):
        _post([{"id": "Construction", "cells": {"pct_in_use": pct}}])
    assert db.upserted == [] and db.deleted == []


def test_post_without_rows_is_rejected(loads, db) -> None:
    with pytest.raises(ValueError, match="rows is required"):
        page.assets_in_use_post("AAPL", {})
