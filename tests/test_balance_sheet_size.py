from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.models.statement import Statement
from src.web.adjusted_statements import Loaded
from src.web.routes.wizard_pages import business_understanding
from src.web.settings import Settings, resolve
from src.web.wizard_registry import get_subpage
from tests.statement_fixtures import P1, P2, P3, _row

A = "us-gaap_Assets"
LE = "us-gaap_LiabilitiesAndStockholdersEquity"
SE = "us-gaap_StockholdersEquity"


def _balance() -> Statement:
    def row(concept, label, parent, v1, v2=None, **kw):
        return _row(
            concept,
            label,
            parent_concept=parent,
            **{P1: v1, P2: v1 if v2 is None else v2, P3: v1},
            **kw,
        )

    rows = [
        row("us-gaap_AssetsCurrent", "Total current assets", A, 90.0),
        row("Cash", "Cash", "us-gaap_AssetsCurrent", 60.0),
        row("Receivables", "Receivables", "us-gaap_AssetsCurrent", 30.0),
        row("Goodwill", "Goodwill", A, 10.0),
        row("Zero", "Zero asset", A, 0.0),
        row(A, "Total assets", None, 100.0),
        row("Debt", "Debt", "us-gaap_Liabilities", 20.0),
        row("us-gaap_Liabilities", "Total liabilities", LE, 20.0),
        row("Common", "Common stock", SE, 100.0),
        row("Treasury", "Treasury stock", SE, -30.0),
        row("Aoci", "AOCI", SE, -10.0),
        row(SE, "Total equity", LE, 60.0),
        row(LE, "Total L&E", None, 80.0),
        row("Shares", "Shares outstanding", None, 5.0),
    ]
    edges = pd.DataFrame(
        [
            {
                "period": p,
                "concept": r["concept"],
                "parent_concept": r["parent_concept"],
                "weight": 1.0,
            }
            for r in rows
            for p in (P1, P2, P3)
            if r["parent_concept"]
        ]
    )
    return Statement(pd.DataFrame(rows), "balance", calc_edges=edges)


def _settings(**values: object) -> Settings:
    decl = get_subpage("business-understanding", "balance-sheet-size").settings
    return resolve(json.dumps(values), decl)


def _use(monkeypatch: pytest.MonkeyPatch, stmt: Statement) -> list[tuple]:
    calls: list[tuple] = []

    def fake_load(ticker, period, basis):
        calls.append((period, basis))
        return Loaded(SimpleNamespace(balance=stmt), [])

    monkeypatch.setattr(business_understanding, "load_for_basis", fake_load)
    return calls


@pytest.fixture
def balance_builder(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    return _use(monkeypatch, _balance())


def _items(table: dict) -> list[tuple[str, float]]:
    return [(r["label"], r["cells"]["value"]) for r in table["rows"]]


def test_context_splits_sides_and_picks_leaves(balance_builder):
    ctx = business_understanding.balance_sheet_size_context("TEST", _settings())
    assert ctx["as_of"] == P1
    sides = ctx["sides"]
    # subtotals, zero leaf and share count are out; ranked desc
    assert _items(sides["assets"]) == [
        ("Cash", 60.0),
        ("Receivables", 30.0),
        ("Goodwill", 10.0),
    ]
    # equity netted: 100 - 30 - 10
    assert _items(sides["liabilities"]) == [("Equity", 60.0), ("Debt", 20.0)]
    assert sides["liabilities"]["rows"][0]["id"] == "equity"
    assert sides["assets"]["columns"][0]["id"] == "value"


def test_loads_annual_on_the_chosen_basis(balance_builder):
    business_understanding.balance_sheet_size_context("TEST", _settings())
    business_understanding.balance_sheet_size_context(
        "TEST", _settings(basis="adjusted", period="quarterly")
    )
    assert balance_builder == [("annual", "reported"), ("annual", "adjusted")]


def test_current_period_offset_picks_and_clamps_the_snapshot(balance_builder):
    ctx = business_understanding.balance_sheet_size_context(
        "TEST", _settings(current_period=1)
    )
    assert ctx["as_of"] == P2
    assert _items(ctx["sides"]["liabilities"])[1] == ("Debt", 20.0)
    far = business_understanding.balance_sheet_size_context(
        "TEST", _settings(current_period=40)
    )
    assert far["as_of"] == P3


def _wide_balance() -> Statement:
    stmt = _balance()
    extra = [
        _row(
            f"Extra{i}",
            f"Extra {i}",
            parent_concept=A,
            **{P1: float(i), P2: 1.0, P3: 1.0},
        )
        for i in range(1, 16)
    ]
    base = stmt.frame[[c for c in stmt.frame.columns if c in _row("c", "c")]]
    frame = pd.concat([base, pd.DataFrame(extra)], ignore_index=True)
    edges = pd.concat(
        [
            stmt.calc_edges,
            pd.DataFrame(
                [
                    {
                        "period": p,
                        "concept": r["concept"],
                        "parent_concept": A,
                        "weight": 1.0,
                    }
                    for r in extra
                    for p in (P1, P2, P3)
                ]
            ),
        ],
        ignore_index=True,
    )
    return Statement(frame, "balance", calc_edges=edges)


@pytest.mark.parametrize("items_per_side", [3, 5, 10])
def test_each_side_is_the_top_items_per_side_ranked_desc(monkeypatch, items_per_side):
    _use(monkeypatch, _wide_balance())
    ctx = business_understanding.balance_sheet_size_context(
        "TEST", _settings(items_per_side=items_per_side)
    )
    values = [v for _, v in _items(ctx["sides"]["assets"])]
    assert len(values) == items_per_side
    assert values == sorted(values, reverse=True)
    assert values[:3] == [60.0, 30.0, 15.0]


def test_negative_equity_omitted(monkeypatch):
    stmt = _balance()
    frame = stmt.frame.copy()
    frame.loc[frame["concept"] == "Common", P1] = 20.0
    _use(monkeypatch, Statement(frame, "balance", calc_edges=stmt.calc_edges))
    sides = business_understanding.balance_sheet_size_context("TEST", _settings())[
        "sides"
    ]
    assert _items(sides["liabilities"]) == [("Debt", 20.0)]
