"""Business Understanding › Balance Sheet Size: builder and page (no network)."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.models.statement import Statement
from src.web.app import app
from src.web.routes.wizard_pages import business_understanding
from tests.statement_fixtures import P1, P2, P3, _row

URL = "/wizard/TEST/business-understanding/balance-sheet-size"
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


@pytest.fixture
def balance_builder(monkeypatch: pytest.MonkeyPatch):
    def fake_load(ticker, period):
        assert period == "annual"
        stmt = _balance()
        return SimpleNamespace(balance=stmt)

    monkeypatch.setattr(business_understanding, "load_statement_set", fake_load)


def _items(table: dict) -> list[tuple[str, float]]:
    return [(r["label"], r["cells"]["value"]) for r in table["rows"]]


def test_context_splits_sides_and_picks_leaves(balance_builder):
    ctx = business_understanding.balance_sheet_size_context("TEST", "quarterly")
    assert ctx["periods"] == [P1, P2, P3]
    snap = ctx["snapshots"][P1]
    # subtotals, zero leaf and share count are out; ranked desc
    assert _items(snap["assets"]) == [
        ("Cash", 60.0),
        ("Receivables", 30.0),
        ("Goodwill", 10.0),
    ]
    # equity netted: 100 - 30 - 10
    assert _items(snap["liabilities"]) == [("Equity", 60.0), ("Debt", 20.0)]
    assert snap["liabilities"]["rows"][0]["id"] == "equity"
    assert snap["assets"]["columns"][0]["id"] == "value"


def test_context_caps_each_side_at_ten_ranked_desc(monkeypatch):
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
    stmt = Statement(frame, "balance", calc_edges=edges)
    monkeypatch.setattr(
        business_understanding,
        "load_statement_set",
        lambda t, p: SimpleNamespace(balance=stmt),
    )
    ctx = business_understanding.balance_sheet_size_context("TEST", "annual")
    assert ctx["max_items_per_side"] == business_understanding.MAX_ITEMS_PER_SIDE == 10
    values = [v for _, v in _items(ctx["snapshots"][P1]["assets"])]
    assert len(values) == 10
    assert values == sorted(values, reverse=True)
    assert values[:3] == [60.0, 30.0, 15.0]


def test_context_exposes_max_items_per_side(balance_builder):
    ctx = business_understanding.balance_sheet_size_context("TEST", "annual")
    assert ctx["max_items_per_side"] == 10


def test_negative_equity_omitted(monkeypatch, balance_builder):
    stmt = _balance()
    frame = stmt.frame.copy()
    frame.loc[frame["concept"] == "Common", P1] = 20.0
    stmt = Statement(frame, "balance", calc_edges=stmt.calc_edges)
    monkeypatch.setattr(
        business_understanding,
        "load_statement_set",
        lambda t, p: SimpleNamespace(balance=stmt),
    )
    snap = business_understanding.balance_sheet_size_context("TEST", "annual")[
        "snapshots"
    ][P1]
    assert _items(snap["liabilities"]) == [("Debt", 20.0)]


def _render(query: str = "") -> str:
    resp = TestClient(app).get(URL + query)
    assert resp.status_code == 200
    return resp.text


def _embedded(html: str, side: str) -> dict:
    m = re.search(rf'id="treemap-data-{side}">(.*?)</script>', html, re.DOTALL)
    assert m
    return json.loads(m.group(1))


def test_page_defaults_and_fallbacks(balance_builder):
    html = _render()
    assert 'data-items-per-side="5"' in html
    assert f'<option value="{P1}" selected>' in html
    assert _items(_embedded(html, "assets"))[0] == ("Cash", 60.0)
    assert '<option value="3"' in html and '<option value="10"' in html
    assert '<option value="11"' not in html

    html = _render(f"?items_per_side=3&as_of={P2}")
    assert 'data-items-per-side="3"' in html
    assert f'<option value="{P2}" selected>' in html

    html = _render("?items_per_side=99&as_of=1999-01-01")
    assert 'data-items-per-side="5"' in html
    assert f'<option value="{P1}" selected>' in html
    assert 'data-items-per-side="5"' in _render("?items_per_side=abc")


def test_only_as_of_select_submits_form(balance_builder):
    html = _render()
    items = re.search(r'<select[^>]*name="items_per_side"[^>]*>', html).group(0)
    as_of = re.search(r'<select[^>]*name="as_of"[^>]*>', html).group(0)
    assert "onchange" not in items
    assert "this.form.submit()" in as_of
