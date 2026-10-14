from __future__ import annotations

import pandas as pd

from src.adjustments.types import owner_earnings as oe
from src.api.edgartools.standard_terms import CFO, NWC_ABSTRACT
from src.models.statement import Statement
from tests.owner_earnings_fixture import CFI, INVENTORIES, PAYABLES, filing
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

CASH_CHANGE = "us-gaap_CashAndCashEquivalentsPeriodIncreaseDecrease"
RESTRICTED_CASH = "us-gaap_IncreaseDecreaseInRestrictedCash"
OTHER_ASSETS = "ext_IncreaseDecreaseInOtherAssets"
PREPAID = "us-gaap_IncreaseDecreaseInPrepaidExpensesOther"
EXPECTED = {
    INVENTORIES: {P1: -4.0, P2: 2.0, P3: -1.0},
    PAYABLES: {P1: 3.0, P2: 1.0, P3: 0.0},
}


def _nwc(frame: pd.DataFrame, calc_edges: pd.DataFrame | None = None) -> dict:
    statement = make_statement(frame, "cashflow")
    if calc_edges is not None:
        statement = Statement(frame, "cashflow", calc_edges=calc_edges)
    rows = oe.nwc_rows(statement).set_index("row_id")
    return {
        row_id: {p: rows.at[row_id, p] for p in statement.periods}
        for row_id in rows.index
    }


def _cashflow() -> pd.DataFrame:
    return filing().cashflow.frame


def test_cfo_total_presented_under_the_working_capital_header_is_not_a_row() -> None:
    frame = _cashflow()
    cfo = frame["concept"].eq(CFO)
    frame.loc[cfo, "parent_abstract_concept"] = NWC_ABSTRACT
    frame.loc[cfo, "parent_concept"] = CASH_CHANGE
    assert _nwc(frame) == EXPECTED


def test_prefix_fallback_skips_change_rows_outside_operating_activities() -> None:
    frame = _cashflow()
    frame["parent_abstract_concept"] = None
    restricted = _row(
        RESTRICTED_CASH, "Restricted cash", weight=-1.0, parent_concept=CFI
    ) | {"row_id": RESTRICTED_CASH, P1: 5.0, P2: 6.0, P3: 7.0}
    frame = pd.concat([frame, pd.DataFrame([restricted])], ignore_index=True)
    assert _nwc(frame) == EXPECTED


def test_period_without_a_calc_tree_takes_the_nearest_periods_weights() -> None:
    frame = _cashflow()
    edges = make_statement(frame, "cashflow").calc_edges
    assert _nwc(frame, edges[edges["period"] != P2]) == EXPECTED


def test_row_with_no_calc_edge_takes_its_sign_from_its_balance_type() -> None:
    frame = _cashflow()
    unplaced = {"parent_abstract_concept": NWC_ABSTRACT, "parent_concept": None}
    signed = _row(OTHER_ASSETS, "Other assets", balance="credit", **unplaced)
    unsigned = _row(PREPAID, "Prepaid expenses", balance=None, **unplaced)
    extra = [
        signed | {"row_id": OTHER_ASSETS, P1: 5.0, P2: 6.0, P3: 7.0},
        unsigned | {"row_id": PREPAID, P1: 1.0, P2: 1.0, P3: 1.0},
    ]
    frame = pd.concat([frame, pd.DataFrame(extra)], ignore_index=True)
    assert _nwc(frame) == EXPECTED | {OTHER_ASSETS: {P1: -5.0, P2: -6.0, P3: -7.0}}
