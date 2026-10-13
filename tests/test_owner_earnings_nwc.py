"""``owner_earnings.nwc_rows`` on filing shapes seen in real cash flows.

The base fixture's ΔNWC is inventories (raw 4, -2, 1 at weight -1) plus
payables (raw 3, 1, 0 at weight +1); each test bends one thing a real filer
does and checks the working-capital rows still come out on the CFO sign.
"""

from __future__ import annotations

import pandas as pd

from src.adjustments.types import owner_earnings as oe
from src.api.edgartools.standard_terms import CFO, NWC_ABSTRACT
from src.models.statement import Statement
from tests.owner_earnings_fixture import CFI, INVENTORIES, PAYABLES, filing
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

CASH_CHANGE = "us-gaap_CashAndCashEquivalentsPeriodIncreaseDecrease"
RESTRICTED_CASH = "us-gaap_IncreaseDecreaseInRestrictedCash"
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
    """MCD presents CFO itself under "changes in operating assets and
    liabilities"; it sums into the cash change, not into CFO."""
    frame = _cashflow()
    cfo = frame["concept"].eq(CFO)
    frame.loc[cfo, "parent_abstract_concept"] = NWC_ABSTRACT
    frame.loc[cfo, "parent_concept"] = CASH_CHANGE
    assert _nwc(frame) == EXPECTED


def test_prefix_fallback_skips_change_rows_outside_operating_activities() -> None:
    """ET has no working-capital header, and its restricted-cash change sums
    into investing activities."""
    frame = _cashflow()
    frame["parent_abstract_concept"] = None
    restricted = _row(
        RESTRICTED_CASH, "Restricted cash", weight=-1.0, parent_concept=CFI
    ) | {"row_id": RESTRICTED_CASH, P1: 5.0, P2: 6.0, P3: 7.0}
    frame = pd.concat([frame, pd.DataFrame([restricted])], ignore_index=True)
    assert _nwc(frame) == EXPECTED


def test_period_without_a_calc_tree_takes_the_nearest_periods_weights() -> None:
    """SBUX FY2018-2021 and O 2012 come from filings whose calc tree has no
    operating section, so the period has no edge for any change row."""
    frame = _cashflow()
    edges = make_statement(frame, "cashflow").calc_edges
    assert _nwc(frame, edges[edges["period"] != P2]) == EXPECTED
