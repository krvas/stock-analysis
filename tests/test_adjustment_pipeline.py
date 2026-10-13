"""The adjustment pipeline on a small hand-built filing, with exact values.

R&D of 30, 60, 90 (2022..2024) capitalized over 3 years, same-year start:
amortization 10, 30, 60 and net capitalized asset 20, 50, 80.
"""

from __future__ import annotations

import dataclasses
import re
from types import SimpleNamespace

import pandas as pd
import pytest

from src.adjustments import engine
from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.registry import ADJUSTMENT_ORDER
from src.adjustments.specs import describe
from src.adjustments.types import assets_in_use, owner_earnings
from src.models.balance_leaves import balance_leaves
from src.models.statement import STATEMENT_TYPES, Statement, StatementSet
from src.web.templating import templates
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

RND = "us-gaap_ResearchAndDevelopmentExpense"
REV = "us-gaap_Revenues"
OI = "us-gaap_OperatingIncomeLoss"
PRETAX = "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
NI = "us-gaap_NetIncomeLoss"
ASSETS = "us-gaap_Assets"
NONCURRENT = "us-gaap_AssetsNoncurrent"
EQUITY = "us-gaap_StockholdersEquity"
LE = "us-gaap_LiabilitiesAndStockholdersEquity"
CFO = "us-gaap_NetCashProvidedByUsedInOperatingActivities"
CFI = "us-gaap_NetCashProvidedByUsedInInvestingActivities"
DA = "us-gaap_DepreciationDepletionAndAmortization"
CASH_CHANGE = "us-gaap_CashPeriodIncreaseDecrease"

AMORTIZATION = "adj_AmortizationResearchAndDevelopmentExpense"
CAPITALIZED = "adj_CapitalizedResearchAndDevelopmentExpense"
EQUITY_OFFSET = "adj_EquityCapitalizedResearchAndDevelopmentExpense"

SPEND = {P3: 30.0, P2: 60.0, P1: 90.0}
AMORT = {P3: 10.0, P2: 30.0, P1: 60.0}
NET = {P3: 20.0, P2: 50.0, P1: 80.0}
OPEX_SPEC = AdjustmentSpec("opex_to_capex", {"rows": {RND: 3}})
OE_SPEC = AdjustmentSpec(owner_earnings.TYPE_ID, {AMORTIZATION: 50.0})
AIU_SPEC = AdjustmentSpec(assets_in_use.TYPE_ID, {CAPITALIZED: 100.0})
# Out of pipeline order on purpose: the engine sorts them.
ALL_SPECS = [AIU_SPEC, OE_SPEC, OPEX_SPEC]


def _values(p1: float, p2: float, p3: float) -> dict[str, float]:
    return {P1: p1, P2: p2, P3: p3}


INCOME = [
    (REV, "Revenue", "Revenue", OI, 1.0, _values(250, 220, 200)),
    (
        RND,
        "Research and development",
        "ResearchAndDevelopmentExpenses",
        OI,
        -1.0,
        _values(90, 60, 30),
    ),
    (
        OI,
        "Operating income",
        "OperatingIncomeLoss",
        PRETAX,
        1.0,
        _values(160, 160, 170),
    ),
    (PRETAX, "Pretax income", "PretaxIncomeLoss", NI, 1.0, _values(160, 160, 170)),
    (NI, "Net income", "NetIncomeLoss", None, 1.0, _values(160, 160, 170)),
]
BALANCE = [
    ("us-gaap_Cash", "Cash", None, ASSETS, 1.0, _values(500, 450, 400)),
    (
        "us-gaap_PropertyPlantAndEquipmentNet",
        "PP&E",
        None,
        NONCURRENT,
        1.0,
        _values(100, 100, 100),
    ),
    (NONCURRENT, "Total non-current assets", None, ASSETS, 1.0, _values(100, 100, 100)),
    (ASSETS, "Total assets", None, None, 1.0, _values(600, 550, 500)),
    ("us-gaap_Liabilities", "Total liabilities", None, LE, 1.0, _values(200, 200, 200)),
    (
        "us-gaap_CommonStockValue",
        "Common stock",
        None,
        EQUITY,
        1.0,
        _values(400, 350, 300),
    ),
    (EQUITY, "Total equity", None, LE, 1.0, _values(400, 350, 300)),
    (LE, "Total liabilities and equity", None, None, 1.0, _values(600, 550, 500)),
]
CASHFLOW = [
    (NI, "Net income", "NetIncomeLoss", CFO, 1.0, _values(160, 160, 170)),
    (
        DA,
        "Depreciation and amortization",
        "DepreciationExpense",
        CFO,
        1.0,
        _values(15, 15, 15),
    ),
    (CFO, "Cash from operations", None, CASH_CHANGE, 1.0, _values(175, 175, 185)),
    (
        "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
        "Capex",
        None,
        CFI,
        -1.0,
        _values(40, 40, 40),
    ),
    (CFI, "Cash from investing", None, CASH_CHANGE, 1.0, _values(-40, -40, -40)),
    (CASH_CHANGE, "Change in cash", None, None, 1.0, _values(135, 135, 145)),
]


def _statement(rows: list, statement_type: str):
    frame = pd.DataFrame(
        [
            _row(
                c,
                label,
                standard_concept=std,
                parent_concept=parent,
                weight=weight,
                **values,
            )
            for c, label, std, parent, weight, values in rows
        ]
    )
    return make_statement(frame, statement_type)


def filing(
    income: list = INCOME, balance: list = BALANCE, cashflow: list = CASHFLOW
) -> StatementSet:
    return StatementSet(
        income=_statement(income, "income"),
        balance=_statement(balance, "balance"),
        cashflow=_statement(cashflow, "cashflow"),
    )


def _without(rows: list, concept: str) -> list:
    """``rows`` minus ``concept``, its children moved up to its parent."""
    parent = next(r[3] for r in rows if r[0] == concept)
    return [
        (c, label, std, parent if p == concept else p, weight, values)
        for c, label, std, p, weight, values in rows
        if c != concept
    ]


def value(ss: StatementSet, statement: str, row_id: str) -> dict[str, float]:
    frame = ss.get(statement).frame.set_index("row_id")
    return {p: round(float(frame.at[row_id, p]), 9) for p in (P1, P2, P3)}


def delta(after: StatementSet, before: StatementSet, statement: str, row_id: str):
    a, b = value(after, statement, row_id), value(before, statement, row_id)
    return {p: round(a[p] - b[p], 9) for p in a}


def test_opex_to_capex_restates_every_statement_in_every_period() -> None:
    base = filing()
    run = apply_adjustments(base, [OPEX_SPEC])
    assert run.applied == (OPEX_SPEC,) and run.skipped == ()
    adjusted = run.statements

    assert value(adjusted, "income", RND) == _values(0, 0, 0)
    assert value(adjusted, "income", AMORTIZATION) == AMORT
    spend_less_amort = {P1: 30.0, P2: 30.0, P3: 20.0}
    assert delta(adjusted, base, "income", OI) == spend_less_amort
    assert delta(adjusted, base, "income", NI) == spend_less_amort

    assert value(adjusted, "balance", CAPITALIZED) == NET
    assert value(adjusted, "balance", EQUITY_OFFSET) == NET
    assert delta(adjusted, base, "balance", NONCURRENT) == NET
    assert delta(adjusted, base, "balance", ASSETS) == NET
    assert delta(adjusted, base, "balance", EQUITY) == NET
    assert delta(adjusted, base, "balance", LE) == NET

    assert value(adjusted, "cashflow", NI) == value(adjusted, "income", NI)
    assert value(adjusted, "cashflow", AMORTIZATION) == AMORT
    assert value(adjusted, "cashflow", CAPITALIZED) == SPEND
    assert delta(adjusted, base, "cashflow", CFO) == SPEND
    assert delta(adjusted, base, "cashflow", CFI) == {p: -v for p, v in SPEND.items()}
    assert delta(adjusted, base, "cashflow", CASH_CHANGE) == _values(0, 0, 0)


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ({"us-gaap_Gone": 3}, "saved row us-gaap_Gone is not in this filing"),
        ({}, "it changed nothing in these statements"),
    ],
)
def test_opex_spec_that_changes_nothing_is_skipped_with_its_reason(
    rows: dict, reason: str
) -> None:
    spec = AdjustmentSpec("opex_to_capex", {"rows": rows})
    run = apply_adjustments(filing(), [spec])
    assert run.applied == ()
    assert [(s.spec, s.reason) for s in run.skipped] == [(spec, reason)]
    assert value(run.statements, "income", RND) == _values(90, 60, 30)


def test_opex_spec_with_one_missing_row_applies_the_rest_and_names_the_gap() -> None:
    spec = AdjustmentSpec("opex_to_capex", {"rows": {RND: 3, "us-gaap_Gone": 5}})
    run = apply_adjustments(filing(), [spec])
    assert run.applied == (AdjustmentSpec("opex_to_capex", {"rows": {RND: 3}}),)
    assert [s.reason for s in run.skipped] == [
        "saved row us-gaap_Gone is not in this filing"
    ]
    assert value(run.statements, "income", AMORTIZATION) == AMORT


def _assert_same_statements(a: StatementSet, b: StatementSet) -> None:
    for st in STATEMENT_TYPES:
        pd.testing.assert_frame_equal(a.get(st).frame, b.get(st).frame)
        pd.testing.assert_frame_equal(a.get(st).calc_edges, b.get(st).calc_edges)


@pytest.mark.parametrize("stage", ADJUSTMENT_ORDER)
def test_until_a_type_applies_only_the_types_before_it(stage: str) -> None:
    before = ADJUSTMENT_ORDER[: ADJUSTMENT_ORDER.index(stage)]
    staged = apply_adjustments(filing(), ALL_SPECS, until=stage)
    assert [s.type_id for s in staged.applied] == list(before)
    assert staged.skipped == ()
    only_before = [s for s in ALL_SPECS if s.type_id in before]
    _assert_same_statements(
        staged.statements, apply_adjustments(filing(), only_before).statements
    )


def test_stacked_pipeline_feeds_capitalized_opex_into_later_types() -> None:
    run = apply_adjustments(filing(), ALL_SPECS)
    assert run.applied == (OPEX_SPEC, OE_SPEC, AIU_SPEC) and run.skipped == ()
    adjusted = run.statements

    items = owner_earnings.da_items(adjusted.cashflow).set_index("row_id")
    assert {p: items.at[AMORTIZATION, p] for p in (P1, P2, P3)} == AMORT
    # Pretax 190 each year after capitalizing; D&A is 15 + amortization;
    # maintenance is 50% of the amortization.
    assert value(adjusted, "cashflow", "adj_MaintenanceCapex") == _values(30, 15, 5)
    assert value(adjusted, "cashflow", "adj_OwnerEarnings") == _values(235, 220, 210)

    total_assets = _values(680, 600, 520)
    assert value(adjusted, "balance", ASSETS) == total_assets
    for period, net in NET.items():
        leaves = {
            leaf.row_id: leaf for leaf in balance_leaves(adjusted.balance, period)
        }
        assert leaves[CAPITALIZED].side == "assets"
        assert leaves[CAPITALIZED].contribution == pytest.approx(net)
    assert value(adjusted, "balance", assets_in_use.GROSS_CONCEPT) == total_assets
    assert value(adjusted, "balance", assets_in_use.NET_CONCEPT) == total_assets


def test_opex_row_with_no_reported_values_is_skipped_and_left_out() -> None:
    sga = "us-gaap_SellingGeneralAndAdministrativeExpense"
    income = [*INCOME, (sga, "SG&A", None, OI, -1.0, {})]
    spec = AdjustmentSpec("opex_to_capex", {"rows": {RND: 3, sga: 5}})
    run = apply_adjustments(filing(income), [spec])
    assert [s.reason for s in run.skipped] == ["SG&A has no reported values"]
    assert [s.params["rows"] for s in run.applied] == [{RND: 3}]


@pytest.mark.parametrize("error", [AttributeError, TypeError])
def test_programmer_errors_in_a_type_propagate(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    def apply(ss, spec):
        raise error("bug")

    monkeypatch.setattr(
        engine, "get_adjustment_type", lambda _: SimpleNamespace(apply=apply)
    )
    with pytest.raises(error):
        apply_adjustments(filing(), [OPEX_SPEC])


@pytest.mark.parametrize(
    ("percent", "shown"), [(100.0, []), (40.0, ["balance sheet has no total assets"])]
)
def test_note_hides_a_skip_whose_spec_changes_nothing(
    percent: float, shown: list[str]
) -> None:
    spec = AdjustmentSpec(assets_in_use.TYPE_ID, {"us-gaap_Cash": percent})
    run = apply_adjustments(filing(balance=_without(BALANCE, ASSETS)), [spec])
    assert [s.reason for s in run.skipped] == ["balance sheet has no total assets"]
    assert [s["reason"] for s in describe(run)["skipped"]] == shown


def _notes(run) -> list[str]:
    html = templates.get_template("shared/_adjustments_note.html").render(
        basis="adjusted", adjustments=describe(run)
    )
    notes = re.findall(r'class="adjustments-note[^"]*">(.*?)</p>', html, re.DOTALL)
    return [" ".join(note.split()) for note in notes]


def test_note_names_a_missing_lookup_in_a_sentence() -> None:
    run = apply_adjustments(filing(_without(INCOME, PRETAX)), [OE_SPEC])
    assert _notes(run) == [
        "Adjusted basis (no adjustments applied)",
        "Not applied: Owner earnings: could not find nwc in these statements",
    ]


CONTINUING = "us-gaap_IncomeLossFromContinuingOperations"
CFO_CONTINUING = f"{CFO}ContinuingOperations"
PARTNERS = "us-gaap_PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest"
PROFIT = "us-gaap_ProfitLoss"
OPEX = "us-gaap_OperatingExpenses"


def _renamed(rows: list, old: str, new: str) -> list:
    return [
        (new if c == old else c, label, std, new if p == old else p, weight, values)
        for c, label, std, p, weight, values in rows
    ]


def _with_parent(rows: list, child: str, concept: str) -> list:
    """``rows`` with ``concept`` inserted between ``child`` and its parent."""
    out = []
    for c, label, std, p, weight, values in rows:
        if c == child:
            out.append((c, label, std, concept, weight, values))
            out.append((concept, concept, None, p, 1.0, values))
        else:
            out.append((c, label, std, p, weight, values))
    return out


def _restates_every_period(run, base: StatementSet, cfo: str, equity: str) -> None:
    assert run.applied == (OPEX_SPEC,) and run.skipped == ()
    adjusted = run.statements
    assert delta(adjusted, base, "balance", ASSETS) == NET
    assert delta(adjusted, base, "balance", equity) == NET
    assert delta(adjusted, base, "balance", LE) == NET
    assert delta(adjusted, base, "cashflow", cfo) == SPEND
    assert delta(adjusted, base, "cashflow", CFI) == {p: -v for p, v in SPEND.items()}
    assert delta(adjusted, base, "cashflow", CASH_CHANGE) == _values(0, 0, 0)


def test_opex_hangs_cash_rows_under_continuing_operations_cfo() -> None:
    income = _with_parent(INCOME, PRETAX, CONTINUING)
    cashflow = _renamed(_renamed(CASHFLOW, CFO, CFO_CONTINUING), NI, CONTINUING)
    base = filing(income, cashflow=cashflow)
    run = apply_adjustments(base, [OPEX_SPEC])
    _restates_every_period(run, base, CFO_CONTINUING, EQUITY)
    assert value(run.statements, "cashflow", CONTINUING) == value(
        run.statements, "income", CONTINUING
    )


def test_opex_hangs_the_equity_offset_under_partners_capital() -> None:
    base = filing(balance=_renamed(BALANCE, EQUITY, PARTNERS))
    run = apply_adjustments(base, [OPEX_SPEC])
    _restates_every_period(run, base, CFO, PARTNERS)


def _without_edges(ss: StatementSet, statement: str, keep) -> StatementSet:
    """``ss`` with P2's calc edges on ``statement`` cut down to ``keep(edges)``."""
    st = ss.get(statement)
    edges = st.calc_edges
    cut = edges[(edges["period"] != P2) | keep(edges)]
    return dataclasses.replace(
        ss, **{statement: Statement(st.frame, st.statement_type, cut)}
    )


@pytest.mark.parametrize(
    ("statement", "keep", "reason"),
    [
        (
            "cashflow",
            lambda e: e["period"] != P2,
            "the cash flow statement does not total operating and investing cash",
        ),
        (
            "cashflow",
            lambda e: e["concept"] != NI,
            "the cash flow statement does not start from net income",
        ),
        (
            "balance",
            lambda e: ~e["parent_concept"].isin([ASSETS, NONCURRENT]),
            "the balance sheet does not total its assets and equity",
        ),
        (
            "balance",
            lambda e: e["parent_concept"] != EQUITY,
            "the balance sheet does not total its assets and equity",
        ),
    ],
    ids=["no-cash-flow-tree", "net-income-outside-cfo", "no-asset-total", "no-equity"],
)
def test_opex_leaves_a_period_with_no_parent_as_reported(
    statement: str, keep, reason: str
) -> None:
    base = _without_edges(filing(), statement, keep)
    run = apply_adjustments(base, [OPEX_SPEC])
    assert run.applied == (OPEX_SPEC,)
    assert [s.reason for s in run.skipped] == [
        f"Research and development left as an expense in {P2}: {reason}"
    ]
    adjusted = run.statements
    for st in STATEMENT_TYPES:
        before = base.get(st).frame.set_index("row_id")[P2]
        after = adjusted.get(st).frame.set_index("row_id").loc[before.index, P2]
        pd.testing.assert_series_equal(after, before, check_dtype=False, obj=st)

    # P2's spend stays expensed, so only P3's and P1's spend is capitalized.
    assert value(adjusted, "income", RND) == _values(0, 60, 0)
    net = {P1: 60.0, P2: 0.0, P3: 20.0}
    assert delta(adjusted, base, "balance", ASSETS) == net
    assert delta(adjusted, base, "balance", LE) == net
    spend = {P1: 90.0, P2: 0.0, P3: 30.0}
    assert delta(adjusted, base, "cashflow", CFO) == spend
    assert delta(adjusted, base, "cashflow", CASH_CHANGE) == _values(0, 0, 0)


def _with_p2_edges(ss: StatementSet, statement: str, edit) -> StatementSet:
    """``ss`` with P2's calc edges on ``statement`` replaced by ``edit(edges)``."""
    st = ss.get(statement)
    edges = st.calc_edges
    p2 = edges["period"] == P2
    edited = pd.concat([edges[~p2], edit(edges[p2])], ignore_index=True)
    return dataclasses.replace(
        ss, **{statement: Statement(st.frame, st.statement_type, edited)}
    )


def _edge(concept: str, parent: str, weight: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "period": [P2],
            "concept": [concept],
            "parent_concept": [parent],
            "weight": [weight],
        }
    )


def test_opex_leaves_a_period_that_adds_net_income_twice_as_reported() -> None:
    income = _with_parent(INCOME, PRETAX, PROFIT)
    cashflow = [*CASHFLOW, (PROFIT, "Profit", None, None, 1.0, _values(160, 160, 170))]
    base = _with_p2_edges(
        filing(income, cashflow=cashflow),
        "cashflow",
        lambda e: pd.concat([e, _edge(PROFIT, CFO)]),
    )
    run = apply_adjustments(base, [OPEX_SPEC])
    reason = "the cash flow statement adds net income in more than once"
    assert [s.reason for s in run.skipped] == [
        f"Research and development left as an expense in {P2}: {reason}"
    ]
    spend = {P1: 90.0, P2: 0.0, P3: 30.0}
    assert delta(run.statements, base, "cashflow", CFO) == spend
    assert delta(run.statements, base, "cashflow", CASH_CHANGE) == _values(0, 0, 0)


def test_opex_amortization_takes_the_expense_weight_of_each_period() -> None:
    """R&D sits under a positive-weight expense subtotal only in P2."""
    income = [
        *INCOME[:1],
        (OPEX, "Operating expenses", None, OI, -1.0, _values(90, 60, 30)),
        *INCOME[1:],
    ]
    base = _with_p2_edges(
        filing(income),
        "income",
        lambda e: pd.concat([e[e["concept"] != RND], _edge(RND, OPEX)]),
    )
    run = apply_adjustments(base, [OPEX_SPEC])
    assert run.skipped == ()
    spend_less_amort = {P1: 30.0, P2: 30.0, P3: 20.0}
    assert delta(run.statements, base, "income", NI) == spend_less_amort
    assert delta(run.statements, base, "cashflow", CFO) == SPEND
