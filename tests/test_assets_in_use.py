"""Assets in use through the adjustments engine, on a fixture balance sheet."""

from __future__ import annotations

import os

import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.specs import describe, from_prefs
from src.adjustments.types.assets_in_use import GROSS_CONCEPT, NET_CONCEPT, TYPE_ID
from src.api.edgartools.source import load_statement_set
from src.config import load_project_dotenv
from src.models.statement import Statement, StatementSet
from tests.statement_fixtures import P1, P2, P3, _income_frame, _row, make_statement
from tests.test_edgar_data import TICKERS_FILE, _test_tickers

A = "us-gaap_Assets"
AC = "us-gaap_AssetsCurrent"
L = "us-gaap_Liabilities"
SE = "us-gaap_StockholdersEquity"
LE = "us-gaap_LiabilitiesAndStockholdersEquity"
CAPITALIZED_RND = "adj_CapitalizedResearchAndDevelopmentExpense"

# concept, label, parent, weight, P1, P2 (P3 is empty: no total assets there)
BALANCE = [
    ("Cash", "Cash", AC, 1.0, 60.0, 50.0),
    ("Receivables", "Receivables", AC, 1.0, 40.0, 30.0),
    ("Allowance", "Allowance for doubtful accounts", AC, -1.0, 5.0, 4.0),
    (AC, "Total current assets", A, 1.0, 95.0, 76.0),
    ("Construction", "Construction in progress", A, 1.0, 50.0, 40.0),
    ("Split", "Leaf in P1, subtotal in P2", A, 1.0, 30.0, 20.0),
    ("SplitA", "Split part A", "Split", 1.0, None, 12.0),
    ("SplitB", "Split part B", "Split", 1.0, None, 8.0),
    (A, "Total assets", None, 1.0, 175.0, 136.0),
    ("Payables", "Accounts payable", L, 1.0, 30.0, 25.0),
    ("Advances", "Customer advances", L, 1.0, 20.0, 15.0),
    ("Debt", "Long-term debt", L, 1.0, 50.0, 40.0),
    (L, "Total liabilities", LE, 1.0, 100.0, 80.0),
    ("Common", "Common stock", SE, 1.0, 75.0, 56.0),
    (SE, "Total equity", LE, 1.0, 75.0, 56.0),
    (LE, "Total liabilities and equity", None, 1.0, 175.0, 136.0),
]


def _balance() -> Statement:
    frame = pd.DataFrame(
        [_row(c, label, **{P1: v1, P2: v2}) for c, label, _, _, v1, v2 in BALANCE]
    )
    edges = pd.DataFrame(
        [
            {"period": p, "concept": c, "parent_concept": parent, "weight": w}
            for c, _, parent, w, v1, v2 in BALANCE
            for p, value in ((P1, v1), (P2, v2), (P3, v1))
            if parent and not (parent == "Split" and value is None)
        ]
    )
    return Statement(frame, "balance", calc_edges=edges)


def _statements() -> StatementSet:
    return StatementSet(
        income=make_statement(_income_frame(), "income"),
        balance=_balance(),
        cashflow=make_statement(_income_frame(), "cashflow"),
    )


def _memo(ss: StatementSet, concept: str) -> dict[str, float | None]:
    frame = ss.balance.frame
    row = frame[frame["concept"] == concept].iloc[0]
    return {p: None if pd.isna(row[p]) else float(row[p]) for p in (P1, P2, P3)}


def _run(params: dict | None = None, *extra: AdjustmentSpec) -> StatementSet:
    specs = [*extra, AdjustmentSpec(TYPE_ID, params or {})]
    return apply_adjustments(_statements(), specs)


def test_saved_defaults_reproduce_total_assets_in_every_period() -> None:
    specs = from_prefs(pd.DataFrame())
    assert specs == [AdjustmentSpec(TYPE_ID, {})]
    adjusted = apply_adjustments(_statements(), specs)
    expected = {P1: 175.0, P2: 136.0, P3: None}
    assert _memo(adjusted, GROSS_CONCEPT) == expected
    assert _memo(adjusted, NET_CONCEPT) == expected


def test_pct_in_use_reduces_gross_by_each_leaf_contribution() -> None:
    adjusted = _run(
        {"Construction": 0.0, "Allowance": 50.0, "Split": 50.0, "Cash": 100.0}
    )
    # P1: 175 - 50 - (-5 * 0.5) - 30 * 0.5; P2: Split has children, so only
    # construction and the contra allowance count: 136 - 40 - (-4 * 0.5)
    assert _memo(adjusted, GROSS_CONCEPT) == {P1: 112.5, P2: 98.0, P3: None}
    assert _memo(adjusted, NET_CONCEPT) == {P1: 112.5, P2: 98.0, P3: None}


def test_netting_reduces_net_only_by_ticked_liabilities() -> None:
    adjusted = _run(
        {
            "Payables": 1.0,
            "Advances": 0.0,
            "Common": 1.0,
            "Vanished": 1.0,
            "AlsoVanished": 0.0,
        }
    )
    assert _memo(adjusted, GROSS_CONCEPT) == {P1: 175.0, P2: 136.0, P3: None}
    assert _memo(adjusted, NET_CONCEPT) == {P1: 145.0, P2: 111.0, P3: None}


def test_capitalized_opex_asset_counts_as_an_asset_leaf() -> None:
    opex = AdjustmentSpec(
        "opex_to_capex", {"rows": {"ResearchAndDevelopmentExpense": 2}}
    )
    # R&D of 10 in P1 over 2 years leaves a net asset of 5, so total assets is 180.
    assert _memo(_run({}, opex), GROSS_CONCEPT)[P1] == 180.0
    assert _memo(_run({CAPITALIZED_RND: 0.0}, opex), GROSS_CONCEPT)[P1] == 175.0


def test_memo_rows_follow_total_assets_and_leave_reported_rows_alone() -> None:
    base = _statements().balance
    adjusted = _run({"Construction": 0.0, "Payables": 1.0}).balance
    frame = adjusted.frame
    row_ids = frame["row_id"].tolist()
    at = row_ids.index(A)
    assert row_ids[at + 1 : at + 3] == [GROSS_CONCEPT, NET_CONCEPT]
    reported = frame[~frame["concept"].isin([GROSS_CONCEPT, NET_CONCEPT])]
    pd.testing.assert_frame_equal(
        reported[[P1, P2, P3]].reset_index(drop=True).astype(float),
        base.frame[[P1, P2, P3]].astype(float),
    )
    edges = adjusted.calc_edges
    assert not edges["concept"].isin([GROSS_CONCEPT, NET_CONCEPT]).any()
    assert not edges["parent_concept"].isin([GROSS_CONCEPT, NET_CONCEPT]).any()


def test_stage_before_assets_in_use_has_no_memo_rows() -> None:
    staged = apply_adjustments(
        _statements(), [AdjustmentSpec(TYPE_ID, {})], until=TYPE_ID
    )
    concepts = set(staged.balance.frame["concept"])
    assert not concepts & {GROSS_CONCEPT, NET_CONCEPT}


def test_default_spec_joins_saved_specs_of_other_types() -> None:
    prefs = pd.DataFrame(
        {
            "adjustment_type": ["owner_earnings"],
            "base_concept": ["maintenance_nwc"],
            "value": [50.0],
        }
    )
    assert [(s.type_id, dict(s.params)) for s in from_prefs(prefs)] == [
        ("owner_earnings", {"maintenance_nwc": 50.0}),
        (TYPE_ID, {}),
    ]


def test_describe_counts_choices_that_differ_from_the_defaults() -> None:
    params = {"Cash": 100.0, "Construction": 0.0, "Payables": 1.0}
    [label] = describe([AdjustmentSpec(TYPE_ID, params)])
    assert label["label"] == "Assets in use: 2 line(s) changed"


def test_default_spec_with_no_saved_choices_is_left_out_of_the_note() -> None:
    assert describe(from_prefs(pd.DataFrame())) == []


def test_balance_sheet_without_total_assets_gets_no_memo_rows() -> None:
    balance = _balance()
    ss = StatementSet(
        income=make_statement(_income_frame(), "income"),
        balance=Statement(
            balance.frame[balance.frame["concept"] != A],
            "balance",
            calc_edges=balance.calc_edges[balance.calc_edges["parent_concept"] != A],
        ),
        cashflow=make_statement(_income_frame(), "cashflow"),
    )
    adjusted = apply_adjustments(ss, [AdjustmentSpec(TYPE_ID, {})])
    concepts = set(adjusted.balance.frame["concept"])
    assert not concepts & {GROSS_CONCEPT, NET_CONCEPT}


@pytest.mark.data
def test_defaults_reproduce_total_assets_on_test_tickers() -> None:
    load_project_dotenv()
    if not os.environ.get("EDGAR_IDENTITY") or not TICKERS_FILE.exists():
        pytest.skip("data test prerequisites missing")
    for ticker in _test_tickers():
        base = load_statement_set(ticker, "annual")
        balance = apply_adjustments(base, from_prefs(pd.DataFrame())).balance
        frame = balance.frame.set_index("row_id")
        for period in base.balance.periods:
            total = frame.at[A, period] if A in frame.index else None
            if total is None or pd.isna(total):
                continue
            assert frame.at[GROSS_CONCEPT, period] == pytest.approx(total), ticker
            assert frame.at[NET_CONCEPT, period] == pytest.approx(total), ticker
            if LE in frame.index and pd.notna(frame.at[LE, period]):
                assert frame.at[LE, period] == pytest.approx(total), ticker
