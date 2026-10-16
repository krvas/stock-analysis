"""``owner_earnings.apply`` on a hand-built filing, with exact values."""

from __future__ import annotations

import pytest

from src.adjustments.base import MEMO_TAG, AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.types import owner_earnings as oe
from src.api.edgartools.standard_terms import CFO
from tests.owner_earnings_fixture import (
    CFI,
    DEPRECIATION,
    MAINTENANCE_CAPEX,
    MAINTENANCE_NWC,
    OWNER_EARNINGS,
    SAVED,
    filing,
)
from tests.statement_fixtures import P1, P2, P3

MEMO_ROWS = [
    "adj_MaintenanceCapex",
    "adj_MaintenanceWorkingCapital",
    "adj_OwnerEarnings",
]


def test_apply_adds_memo_rows_with_hand_computed_values() -> None:
    rows = {
        row.concept: row
        for row in oe.apply(filing(), AdjustmentSpec(oe.TYPE_ID, SAVED)).new_rows
    }
    assert list(rows) == MEMO_ROWS
    expected = dict(
        zip(MEMO_ROWS, (MAINTENANCE_CAPEX, MAINTENANCE_NWC, OWNER_EARNINGS))
    )
    for concept, values in expected.items():
        row = rows[concept]
        assert row.statement == "cashflow"
        assert row.values == pytest.approx(values), concept
        assert row.tags == (MEMO_TAG,)
        assert row.parent_concept is None
        assert row.is_total == (concept == "adj_OwnerEarnings")
    assert rows["adj_MaintenanceWorkingCapital"].label == (
        "Maintenance working capital (50% of ΔNWC)"
    )


def test_engine_places_memo_rows_right_after_cfo_and_sums_none_of_them() -> None:
    base = filing()
    spec = AdjustmentSpec(oe.TYPE_ID, SAVED)
    run = apply_adjustments(base, [spec])
    assert run.applied == (spec,) and run.skipped == ()
    cashflow = run.statements.cashflow
    ids = list(cashflow.frame["row_id"])
    cfo = ids.index(CFO)
    assert ids[cfo + 1 : cfo + 5] == [*MEMO_ROWS, CFI]
    assert set(MEMO_ROWS).isdisjoint(cashflow.calc_edges["concept"])
    reported = base.cashflow.frame.set_index("row_id")
    adjusted = cashflow.frame.set_index("row_id")
    for row_id in reported.index:
        for period in base.cashflow.periods:
            assert adjusted.at[row_id, period] == pytest.approx(
                reported.at[row_id, period], nan_ok=True
            ), (row_id, period)


def test_no_pcts_means_owner_earnings_is_pretax_plus_da_plus_nwc() -> None:
    rows = {
        r.concept: r.values
        for r in oe.apply(filing(), AdjustmentSpec(oe.TYPE_ID, {})).new_rows
    }
    assert rows["adj_MaintenanceCapex"] == pytest.approx(
        {p: 0.0 for p in OWNER_EARNINGS}
    )
    assert rows["adj_OwnerEarnings"] == pytest.approx({P1: 129.0, P2: 103.0, P3: 69.0})


@pytest.mark.parametrize(
    ("params", "label"),
    [
        (SAVED, "Owner earnings: maintenance % set on 2 D&A item(s), 50% of ΔNWC"),
        (
            {DEPRECIATION: 10.0},
            "Owner earnings: maintenance % set on 1 D&A item(s), 0% of ΔNWC",
        ),
        (
            {oe.MAINTENANCE_NWC: 12.5},
            "Owner earnings: maintenance % set on 0 D&A item(s), 12.5% of ΔNWC",
        ),
    ],
)
def test_describe_counts_da_items_and_shows_the_nwc_pct(
    params: dict, label: str
) -> None:
    assert oe.describe(AdjustmentSpec(oe.TYPE_ID, params)) == {
        "type": oe.TYPE_ID,
        "label": label,
    }
