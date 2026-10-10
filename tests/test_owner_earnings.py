"""Adjustments › Owner Earnings: context builder honours the period Settings."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.web import adjusted_statements
from src.web.routes.wizard_pages import owner_earnings
from src.web.settings import resolve
from src.web.wizard_registry import get_subpage
from tests.statement_fixtures import P1, P2, P3, _row, make_statement_set


@pytest.fixture(autouse=True)
def statements(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {P1: 10.0, P2: 9.0, P3: 8.0}
    frame = pd.DataFrame(
        [
            _row(
                "Pretax", "Pretax income", standard_concept="PretaxIncomeLoss", **values
            ),
            _row(
                "Dep", "Depreciation", standard_concept="DepreciationExpense", **values
            ),
            _row("us-gaap_IncreaseDecreaseInInventories", "Inventories", **values),
        ]
    )
    monkeypatch.setattr(
        adjusted_statements, "load_statement_set", lambda *_: make_statement_set(frame)
    )
    monkeypatch.setattr(adjusted_statements, "load_specs", lambda _: [])


def _period_columns(table: dict) -> list[str]:
    return [c["id"] for c in table["columns"] if c["kind"] == "static"]


@pytest.mark.parametrize(
    ("num_periods", "expected"), [(1, [P1]), (2, [P1, P2]), (10, [P1, P2, P3])]
)
def test_tables_follow_num_periods(num_periods: int, expected: list[str]) -> None:
    decl = get_subpage("adjustments", "owner-earnings").settings
    settings = resolve(json.dumps({"num_periods": num_periods}), decl)
    ctx = owner_earnings.owner_earnings_context("AAPL", settings)
    assert _period_columns(ctx["oe_table"]) == expected
    assert _period_columns(ctx["nwc_table"]) == expected
