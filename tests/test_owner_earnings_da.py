"""Owner-earnings D&A when the breakdown and the D&A line vary by period.

AAPL's shape: the D&A line is ``DepreciationDepletionAndAmortization`` in
recent years and ``DepreciationAmortizationAndAccretionNet`` before, and the
note components cover only some periods.

- P1: line 30, components depreciation 20 + amortization 10 (complete).
- P2: line 25, no components (AAPL FY2018).
- P3: older line concept 18, only amortization 4 reported (AAPL FY2013-2017).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.adjustments.types import owner_earnings as oe
from src.api.edgartools.standard_terms import CFO, DA_COMPONENT_AXIS
from src.models.statement import StatementSet
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

PRETAX = "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
DA = "us-gaap_DepreciationDepletionAndAmortization"
OLD_DA = "us-gaap_DepreciationAmortizationAndAccretionNet"


def _component(member: str, **values: float) -> dict:
    return _row(
        DA,
        member,
        standard_concept="DepreciationExpense",
        dimension=True,
        is_breakdown=True,
        dimension_axis=DA_COMPONENT_AXIS,
        dimension_member=member,
        parent_concept=CFO,
        **values,
    )


def aapl_shape() -> StatementSet:
    income = pd.DataFrame(
        [
            _row(
                PRETAX,
                "Pretax income",
                standard_concept="PretaxIncomeLoss",
                **{P1: 100.0, P2: 80.0, P3: 60.0},
            )
        ]
    )
    da = {"standard_concept": "DepreciationExpense", "parent_concept": CFO}
    cashflow = pd.DataFrame(
        [
            _row(DA, "Depreciation and amortization", **da, **{P1: 30.0, P2: 25.0}),
            _component("us-gaap_Depreciation", **{P1: 20.0}),
            _component("us-gaap_AmortizationOfIntangibleAssets", **{P1: 10.0, P3: 4.0}),
            _row(
                OLD_DA, "Depreciation, amortization and accretion", **da, **{P3: 18.0}
            ),
            _row(CFO, "Cash from operations", **{P1: 130.0, P2: 105.0, P3: 78.0}),
        ]
    )
    return StatementSet(
        income=make_statement(income, "income"),
        balance=make_statement(income.iloc[0:0], "balance"),
        cashflow=make_statement(cashflow, "cashflow"),
    )


@pytest.mark.xfail(strict=True, reason="D&A undercount in older periods")
def test_da_matches_the_da_line_in_every_period() -> None:
    da = oe.components(aapl_shape())["da"]
    assert da.to_dict() == pytest.approx({P1: 30.0, P2: 25.0, P3: 18.0})
