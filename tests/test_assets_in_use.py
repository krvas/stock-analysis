from __future__ import annotations

import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.specs import describe, from_prefs
from src.adjustments.types.assets_in_use import GROSS_CONCEPT, NET_CONCEPT, TYPE_ID
from src.api.edgartools.source import load_statement_set
from src.models.balance_leaves import balance_leaves
from src.models.statement import Statement, StatementSet
from src.web.routes.wizard_pages.business_understanding import fund_flow_table
from tests import test_adjustment_pipeline as pipeline
from tests.statement_fixtures import P1, P2, P3, _income_frame, _row, make_statement

A = "us-gaap_Assets"
AC = "us-gaap_AssetsCurrent"
L = "us-gaap_Liabilities"
SE = "us-gaap_StockholdersEquity"
LE = "us-gaap_LiabilitiesAndStockholdersEquity"
CAPITALIZED_RND = "adj_CapitalizedResearchAndDevelopmentExpense"

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
    return apply_adjustments(_statements(), specs).statements


def test_saved_defaults_reproduce_total_assets_in_every_period() -> None:
    specs = from_prefs(pd.DataFrame())
    assert specs == [AdjustmentSpec(TYPE_ID, {})]
    adjusted = apply_adjustments(_statements(), specs).statements
    expected = {P1: 175.0, P2: 136.0, P3: None}
    assert _memo(adjusted, GROSS_CONCEPT) == expected
    assert _memo(adjusted, NET_CONCEPT) == expected


def test_pct_in_use_reduces_gross_by_each_leaf_contribution() -> None:
    adjusted = _run(
        {"Construction": 0.0, "Allowance": 50.0, "Split": 50.0, "Cash": 100.0}
    )
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
    def gross(params: dict) -> dict[str, float]:
        specs = [pipeline.OPEX_SPEC, AdjustmentSpec(TYPE_ID, params)]
        run = apply_adjustments(pipeline.filing(), specs)
        return pipeline.value(run.statements, "balance", GROSS_CONCEPT)

    reported = pipeline.value(pipeline.filing(), "balance", pipeline.ASSETS)
    with_opex = {p: v + pipeline.NET[p] for p, v in reported.items()}
    assert gross({}) == with_opex
    assert gross({CAPITALIZED_RND: 0.0}) == reported


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


def test_fund_flow_leaves_out_the_memo_rows() -> None:
    table = fund_flow_table(_run().balance, "detailed", P1, P2).serialize()
    ids = {row["id"] for row in table["rows"]}
    assert A in ids and not ids & {GROSS_CONCEPT, NET_CONCEPT}


def test_stage_before_assets_in_use_has_no_memo_rows() -> None:
    staged = apply_adjustments(
        _statements(), [AdjustmentSpec(TYPE_ID, {})], until=TYPE_ID
    ).statements
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
    note = describe(apply_adjustments(_statements(), [AdjustmentSpec(TYPE_ID, params)]))
    assert note == {
        "applied": [{"type": TYPE_ID, "label": "Assets in use: 2 line(s) changed"}],
        "skipped": [],
    }


@pytest.mark.parametrize("params", [{}, {"Cash": 100.0, "Payables": 100.0}])
def test_spec_with_no_choice_off_the_defaults_is_left_out_of_the_note(
    params: dict,
) -> None:
    run = apply_adjustments(_statements(), [AdjustmentSpec(TYPE_ID, params)])
    assert describe(run) == {"applied": [], "skipped": []}


def test_default_spec_with_no_saved_choices_is_left_out_of_the_note() -> None:
    run = apply_adjustments(_statements(), from_prefs(pd.DataFrame()))
    assert describe(run) == {"applied": [], "skipped": []}


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
    run = apply_adjustments(ss, [AdjustmentSpec(TYPE_ID, {})])
    concepts = set(run.statements.balance.frame["concept"])
    assert not concepts & {GROSS_CONCEPT, NET_CONCEPT}
    assert [s.reason for s in run.skipped] == ["balance sheet has no total assets"]


@pytest.mark.data
def test_defaults_reproduce_total_assets_on_test_tickers(data_ticker: str) -> None:
    base = load_statement_set(data_ticker, "annual")
    balance = apply_adjustments(base, from_prefs(pd.DataFrame())).statements.balance
    frame = balance.frame.set_index("row_id")
    for period in base.balance.periods:
        total = frame.at[A, period] if A in frame.index else None
        if total is None or pd.isna(total):
            continue
        assert frame.at[GROSS_CONCEPT, period] == pytest.approx(total), data_ticker
        assert frame.at[NET_CONCEPT, period] == pytest.approx(total), data_ticker
        if LE in frame.index and pd.notna(frame.at[LE, period]):
            assert frame.at[LE, period] == pytest.approx(total), data_ticker


def test_a_leaf_summed_into_two_totals_counts_once_toward_total_assets() -> None:
    # JPM's balance sheet: loans and their allowance sum into both the net
    # loans line and Assets; the net loans line is not itself under Assets.
    net = "us-gaap_LoansReceivableNet"
    rows = [
        ("Cash", "Cash", 50.0),
        ("Loans", "Loans", 100.0),
        ("Allowance", "Allowance for loan losses", 10.0),
        (net, "Loans, net", 90.0),
        (A, "Total assets", 140.0),
    ]
    frame = pd.DataFrame([_row(c, label, **{P1: v}) for c, label, v in rows])
    arcs = [
        ("Loans", net, 1.0),
        ("Allowance", net, -1.0),
        ("Cash", A, 1.0),
        ("Loans", A, 1.0),
        ("Allowance", A, -1.0),
    ]
    edges = pd.DataFrame(
        [
            {"period": P1, "concept": c, "parent_concept": p, "weight": w}
            for c, p, w in arcs
        ]
    )
    balance = Statement(frame, "balance", calc_edges=edges)

    leaves = balance_leaves(balance, P1)

    assert {leaf.row_id: (leaf.side, leaf.chain_weight) for leaf in leaves} == {
        "Cash": ("assets", 1.0),
        "Loans": ("assets", 1.0),
        "Allowance": ("assets", -1.0),
    }
    assert sum(leaf.contribution for leaf in leaves) == 140.0
