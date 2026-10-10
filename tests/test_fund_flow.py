"""Business Understanding › Fund Flow: table and context builder (no network)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.models.statement import Statement, StatementSet
from src.web import adjusted_statements
from src.web.routes.wizard_pages import business_understanding
from src.web.settings import Settings, resolve
from src.web.wizard_registry import get_subpage
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

P4 = "2021-12-31"


def _balance() -> Statement:
    rows = [
        _row("Cash", "Cash", level=0, **{P1: 50.0, P2: 30.0, P3: 20.0, P4: 10.0}),
        _row(
            "Debt",
            "Debt",
            level=0,
            preferred_sign=-1.0,
            **{P1: 40.0, P2: 45.0, P3: None, P4: 5.0},
        ),
        _row(
            "Cash",
            "Cash, US",
            dimension=True,
            is_breakdown=True,
            dimension_axis="StatementGeographicalAxis",
            dimension_member="US",
            **{P1: 20.0, P2: 10.0, P3: 5.0, P4: 1.0},
        ),
    ]
    return make_statement(pd.DataFrame(rows), "balance")


def _settings(**values: object) -> Settings:
    decl = get_subpage("business-understanding", "fund-flow").settings
    return resolve(json.dumps(values), decl)


def _cells(table: dict) -> dict[str, dict]:
    return {row["id"]: row["cells"] for row in table["rows"]}


def test_table_has_current_previous_and_change_on_display_signs() -> None:
    table = business_understanding.fund_flow_table(_balance(), "summary", P1, P2)
    assert [c["id"] for c in table.serialize()["columns"]] == [P1, P2, "change"]
    cells = _cells(table.serialize())
    assert cells["Cash"] == {P1: 50.0, P2: 30.0, "change": 20.0}
    assert cells["Debt"] == {P1: -40.0, P2: -45.0, "change": 5.0}


def test_change_is_missing_when_either_side_is() -> None:
    cells = _cells(
        business_understanding.fund_flow_table(
            _balance(), "summary", P2, P3
        ).serialize()
    )
    assert cells["Debt"][P3] is None and cells["Debt"]["change"] is None


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    calls: list[tuple] = []
    balance = _balance()

    def fake_load(ticker, period):
        calls.append(("load", period))
        return StatementSet(
            income=make_statement(balance.frame, "income"),
            balance=balance,
            cashflow=make_statement(balance.frame, "cashflow"),
        )

    def fake_specs(ticker):
        calls.append(("specs",))
        return [AdjustmentSpec("opex_to_capex", {})]

    monkeypatch.setattr(adjusted_statements, "load_statement_set", fake_load)
    monkeypatch.setattr(adjusted_statements, "load_specs", fake_specs)
    monkeypatch.setattr(adjusted_statements, "apply_adjustments", lambda ss, _: ss)
    return calls


def _context(**values: object) -> dict:
    return business_understanding.fund_flow_context("TEST", _settings(**values))


def _columns(ctx: dict) -> list[str]:
    return [c["id"] for c in ctx["fund_flow_table"]["columns"]]


def test_defaults_compare_latest_with_one_back(loaded) -> None:
    ctx = _context()
    assert _columns(ctx) == [P1, P2, "change"]
    assert ctx["basis"] == "reported" and ctx["adjustments"] == []
    assert loaded == [("load", "annual")]


def test_offsets_pick_the_two_periods(loaded) -> None:
    assert _columns(_context(current_period=1, previous_period=3)) == [P2, P4, "change"]


def test_offsets_clamp_to_the_oldest_period(loaded) -> None:
    assert _columns(_context(current_period=2, previous_period=40)) == [
        P3,
        P4,
        "change",
    ]


@pytest.mark.parametrize(
    "values", [{"current_period": 3, "previous_period": 9}, {"current_period": 9}]
)
def test_offsets_clamping_to_one_period_show_the_notice(loaded, values) -> None:
    ctx = _context(**values)
    assert ctx["not_enough_periods"] is True
    assert "fund_flow_table" not in ctx


def test_view_and_period_type_follow_settings(loaded) -> None:
    detailed = _context(view="detailed", period="quarterly")
    assert "Cash|StatementGeographicalAxis=US" in _cells(detailed["fund_flow_table"])
    summary = _cells(_context(view="summary")["fund_flow_table"])
    assert set(summary) == {"Cash", "Debt"}
    assert ("load", "quarterly") in loaded


def test_adjusted_basis_loads_saved_adjustments(loaded) -> None:
    ctx = _context(basis="adjusted")
    assert ctx["basis"] == "adjusted"
    assert [a["label"] for a in ctx["adjustments"]] == ["Opex capitalized (0)"]
    assert ("specs",) in loaded


def test_single_period_ticker_shows_the_notice(monkeypatch) -> None:
    frame = _balance().frame.drop(columns=[P2, P3, P4])
    single = make_statement(frame, "balance")
    monkeypatch.setattr(
        adjusted_statements,
        "load_statement_set",
        lambda *_: StatementSet(
            income=make_statement(frame, "income"),
            balance=single,
            cashflow=make_statement(frame, "cashflow"),
        ),
    )
    assert _context()["not_enough_periods"] is True
