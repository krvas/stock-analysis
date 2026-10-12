"""The adjustment pipeline on a small hand-built filing, with exact values.

R&D of 30, 60, 90 (2022..2024) capitalized over 3 years, same-year start:
amortization 10, 30, 60 and net capitalized asset 20, 50, 80.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.registry import ADJUSTMENT_ORDER
from src.adjustments.types import assets_in_use, owner_earnings
from src.models.balance_leaves import balance_leaves
from src.models.statement import STATEMENT_TYPES, StatementSet
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


def filing() -> StatementSet:
    return StatementSet(
        income=_statement(INCOME, "income"),
        balance=_statement(BALANCE, "balance"),
        cashflow=_statement(CASHFLOW, "cashflow"),
    )


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
    assert run.applied == (spec,)
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
