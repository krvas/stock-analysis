"""A small filing for owner earnings, with hand-computed results.

Pretax 100, 80, 60 (P1..P3). D&A is reported as two note components,
depreciation 20, 15, 8 and amortization 10, 5, 2. ΔNWC on the CFO sign is
inventories (raw 4, -2, 1 at weight -1) plus payables (raw 3, 1, 0 at
weight +1): -1, 3, -1.

Saved choices (:data:`SAVED`): 60% of depreciation, 20% of amortization and
50% of ΔNWC are maintenance.
"""

from __future__ import annotations

import pandas as pd

from src.adjustments.types import owner_earnings as oe
from src.api.edgartools.standard_terms import (
    CFO,
    DA_COMPONENT_AXIS,
    NWC_ABSTRACT,
)
from src.models.statement import StatementSet
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

PRETAX = "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
NI = "us-gaap_NetIncomeLoss"
DA = "us-gaap_DepreciationDepletionAndAmortization"
INVENTORIES = "us-gaap_IncreaseDecreaseInInventories"
PAYABLES = "us-gaap_IncreaseDecreaseInAccountsPayable"
CFI = "us-gaap_NetCashProvidedByUsedInInvestingActivities"
DEPRECIATION = f"{DA}|{DA_COMPONENT_AXIS}=Depreciation"
AMORTIZATION = f"{DA}|{DA_COMPONENT_AXIS}=Amortization"

SAVED = {DEPRECIATION: 60.0, AMORTIZATION: 20.0, oe.MAINTENANCE_NWC: 50.0}
MAINTENANCE_CAPEX = {P1: 14.0, P2: 10.0, P3: 5.2}
MAINTENANCE_NWC = {P1: -0.5, P2: 1.5, P3: -0.5}
OWNER_EARNINGS = {P1: 115.5, P2: 91.5, P3: 64.3}


def _values(p1: float, p2: float, p3: float) -> dict[str, float]:
    return {P1: p1, P2: p2, P3: p3}


def _component(member: str, values: dict[str, float]) -> dict:
    return _row(
        DA,
        member,
        dimension=True,
        is_breakdown=True,
        dimension_axis=DA_COMPONENT_AXIS,
        dimension_member=member,
        parent_concept=CFO,
        **values,
    )


def filing() -> StatementSet:
    income = pd.DataFrame(
        [
            _row(
                PRETAX,
                "Pretax income",
                standard_concept="PretaxIncomeLoss",
                parent_concept=NI,
                **_values(100, 80, 60),
            ),
            _row(NI, "Net income", **_values(80, 64, 48)),
        ]
    )
    nwc_header = {"parent_abstract_concept": NWC_ABSTRACT, "parent_concept": CFO}
    cashflow = pd.DataFrame(
        [
            _row(NI, "Net income", parent_concept=CFO, **_values(80, 64, 48)),
            _row(
                DA,
                "Depreciation and amortization",
                standard_concept="DepreciationExpense",
                parent_concept=CFO,
                **_values(30, 20, 10),
            ),
            _component("Depreciation", _values(20, 15, 8)),
            _component("Amortization", _values(10, 5, 2)),
            _row(NWC_ABSTRACT, "Changes in working capital", abstract=True),
            _row(
                INVENTORIES,
                "Inventories",
                weight=-1.0,
                **nwc_header,
                **_values(4, -2, 1),
            ),
            _row(PAYABLES, "Accounts payable", **nwc_header, **_values(3, 1, 0)),
            _row(CFO, "Cash from operations", **_values(109, 87, 57)),
            _row(CFI, "Cash from investing", **_values(-40, -40, -40)),
        ]
    )
    return StatementSet(
        income=make_statement(income, "income"),
        balance=make_statement(income.iloc[0:0], "balance"),
        cashflow=make_statement(cashflow, "cashflow"),
    )
