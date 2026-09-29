"""Shared statement test data: period constants and row/frame builders.

Plain helpers (called as functions), imported by the statement test modules.
"""

from __future__ import annotations

import pandas as pd

from src.models.statement import Statement

P1, P2, P3 = "2024-12-31", "2023-12-31", "2022-12-31"


def _row(concept: str, label: str, **overrides) -> dict:
    row = {
        "concept": concept,
        "label": label,
        "standard_concept": None,
        "level": 1,
        "abstract": False,
        "dimension": False,
        "is_breakdown": False,
        "dimension_axis": None,
        "dimension_member": None,
        "dimension_member_label": None,
        "dimension_label": None,
        "balance": "debit",
        "weight": 1.0,
        "preferred_sign": None,
        "parent_concept": None,
        "parent_abstract_concept": None,
        P1: None,
        P2: None,
        P3: None,
    }
    row.update(overrides)
    return row


def _income_frame() -> pd.DataFrame:
    rows = [
        _row("IncomeStatementAbstract", "Income Statement", abstract=True, level=0),
        _row(
            "Revenues",
            "Revenue",
            standard_concept="Revenue",
            balance="credit",
            parent_concept="GrossProfit",
            **{P1: 100.0, P2: 90.0, P3: 80.0},
        ),
        _row(
            "Revenues",
            "Product",
            dimension=True,
            is_breakdown=False,
            dimension_axis="ProductOrServiceAxis",
            dimension_member="ProductMember",
            parent_concept="GrossProfit",
            **{P1: 60.0, P2: 50.0, P3: 40.0},
        ),
        _row(
            "Revenues",
            "US",
            dimension=True,
            is_breakdown=True,
            dimension_axis="StatementGeographicalAxis",
            dimension_member="US",
            parent_concept="GrossProfit",
            **{P1: 70.0, P2: 65.0, P3: 55.0},
        ),
        _row(
            "CostOfRevenue",
            "Cost of revenue",
            standard_concept="CostOfRevenue",
            weight=-1.0,
            preferred_sign=-1.0,
            parent_concept="GrossProfit",
            **{P1: 40.0, P2: 35.0, P3: 30.0},
        ),
        _row(
            "ResearchAndDevelopmentExpense",
            "R&D",
            standard_concept="OperatingExpenses",
            **{P1: 10.0, P2: None, P3: None},
        ),
        _row(
            "SellingGeneralAndAdministrativeExpense",
            "SG&A",
            standard_concept="OperatingExpenses",
            **{P1: None, P2: None, P3: 5.0},
        ),
        _row(
            "GrossProfit",
            "Total gross profit",
            standard_concept="GrossProfit",
            level=0,
            **{P1: 60.0, P2: 55.0, P3: 50.0},
        ),
    ]
    for row in rows[1:]:
        row["parent_abstract_concept"] = "IncomeStatementAbstract"
    return pd.DataFrame(rows)


def _income() -> Statement:
    return Statement(_income_frame(), "income")
