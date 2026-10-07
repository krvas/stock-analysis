"""Shared statement test data: period constants and row/frame builders.

Plain helpers (called as functions), imported by the statement test modules.
"""

from __future__ import annotations

import pandas as pd

from src.models.statement import (
    CALC_EDGE_COLUMNS,
    STATEMENT_METADATA_COLUMNS,
    STATEMENT_TYPES,
    Statement,
    StatementSet,
    StatementType,
)
from src.utils.text import clean_str

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


def derived_calc_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """Calc edges of a single-filing frame, from its own columns.

    Every non-dimensional row with a ``parent_concept`` and a known ``weight``
    (1 when there is no ``weight`` column) becomes an edge in every period
    column; a concept presented twice keeps its first row's edge.
    """
    periods = [c for c in frame.columns if c not in STATEMENT_METADATA_COLUMNS]
    if "parent_concept" not in frame.columns or not periods:
        return pd.DataFrame(
            {
                c: pd.Series(dtype=float if c == "weight" else str)
                for c in CALC_EDGE_COLUMNS
            }
        )
    if "dimension" in frame.columns:
        rows = frame[~frame["dimension"].fillna(False).astype(bool)]
    else:
        rows = frame
    if "weight" in rows.columns:
        weights = pd.to_numeric(rows["weight"], errors="coerce").astype(float)
    else:
        weights = pd.Series(1.0, index=rows.index)
    edges = pd.DataFrame(
        {
            "concept": rows["concept"].map(clean_str),
            "parent_concept": rows["parent_concept"].map(clean_str),
            "weight": weights,
        }
    )
    edges = edges.dropna().drop_duplicates("concept", keep="first")
    out = pd.concat([edges.assign(period=p) for p in periods], ignore_index=True)
    out = out.loc[:, list(CALC_EDGE_COLUMNS)]
    for col in ("period", "concept", "parent_concept"):
        out[col] = out[col].astype(str)
    out["weight"] = out["weight"].astype(float)
    return out


def make_statement(frame: pd.DataFrame, statement_type: StatementType) -> Statement:
    """A :class:`Statement` whose calc edges are derived from ``frame``."""
    return Statement(frame, statement_type, calc_edges=derived_calc_edges(frame))


def make_statement_set(
    frame: pd.DataFrame, calc_edges: pd.DataFrame | None = None
) -> StatementSet:
    """A :class:`StatementSet` whose three statements all use ``frame``; calc
    edges are ``calc_edges`` when given, else derived from ``frame``."""
    if calc_edges is None:
        calc_edges = derived_calc_edges(frame)
    return StatementSet(
        **{st: Statement(frame, st, calc_edges=calc_edges) for st in STATEMENT_TYPES}
    )


def _income() -> Statement:
    return make_statement(_income_frame(), "income")
