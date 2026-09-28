"""Tests for the Statement / StatementSet domain model."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.models.statement import (
    PROJECTION_METADATA_COLUMNS,
    DuplicateRowIdError,
    Statement,
    StatementSet,
    get_row_id,
    is_total_label,
)
from src.models.table import STATEMENT_VIEW_METADATA_COLUMNS

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
    return pd.DataFrame(rows)


def _income() -> Statement:
    return Statement(_income_frame(), "income")


# --- get_row_id --------------------------------------------------------------


def test_get_row_id_plain_row_is_concept() -> None:
    assert get_row_id({"concept": "Revenues"}) == "Revenues"
    assert get_row_id(pd.Series({"concept": "Revenues"})) == "Revenues"


def test_get_row_id_dimensional_row_includes_axis_and_member() -> None:
    row = pd.Series(
        {
            "concept": "Revenues",
            "dimension_axis": "ProductOrServiceAxis",
            "dimension_member": "ProductMember",
        }
    )
    assert get_row_id(row) == "Revenues|ProductOrServiceAxis=ProductMember"


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA, "", "  "])
def test_get_row_id_treats_missing_dimension_fields_as_absent(missing) -> None:
    row = {
        "concept": "Revenues",
        "dimension_axis": missing,
        "dimension_member": missing,
    }
    assert get_row_id(row) == "Revenues"


def test_get_row_id_requires_concept() -> None:
    with pytest.raises(ValueError):
        get_row_id({"concept": None})


def test_is_total_label() -> None:
    assert is_total_label("Total assets")
    assert is_total_label("Assets, TOTAL")
    assert not is_total_label("Subtotaled items")
    assert not is_total_label(None)


# --- construction ------------------------------------------------------------


def test_constructor_fills_added_columns_without_mutating_input() -> None:
    frame = _income_frame()
    before = frame.copy()
    statement = Statement(frame, "income")

    pd.testing.assert_frame_equal(frame, before)
    df = statement.frame
    assert df["row_id"].tolist()[2] == "Revenues|ProductOrServiceAxis=ProductMember"
    assert (df["origin"] == "reported").all()
    assert all(tags == () for tags in df["tags"])
    assert df.loc[df["concept"] == "GrossProfit", "is_total"].item()
    assert not df.loc[df["concept"] == "Revenues", "is_total"].iloc[0]
    assert statement.periods == [P1, P2, P3]


def test_constructor_normalizes_parquet_style_tags() -> None:
    frame = _income_frame()
    frame["tags"] = [None] * (len(frame) - 1) + [["da", "b"]]
    statement = Statement(frame, "income")
    assert statement.frame["tags"].iloc[-1] == ("b", "da")
    assert statement.frame["tags"].iloc[0] == ()


def test_constructor_raises_on_duplicate_row_ids() -> None:
    frame = pd.DataFrame(
        [_row("Revenues", "Revenue"), _row("Revenues", "Revenue again")]
    )
    with pytest.raises(DuplicateRowIdError, match="Revenues"):
        Statement(frame, "income")


def test_constructor_rejects_unknown_statement_type() -> None:
    with pytest.raises(ValueError):
        Statement(_income_frame(), "equity")  # type: ignore[arg-type]


# --- find / children ---------------------------------------------------------


def test_find_by_standard_concept() -> None:
    rows = _income().find(standard_concept="OperatingExpenses")
    assert rows["concept"].tolist() == [
        "ResearchAndDevelopmentExpense",
        "SellingGeneralAndAdministrativeExpense",
    ]


def test_find_by_concept_excludes_dimensional_by_default() -> None:
    statement = _income()
    assert statement.find(concept="Revenues")["row_id"].tolist() == ["Revenues"]
    assert len(statement.find(concept="Revenues", include_dimensional=True)) == 3


def test_children_via_parent_concept_excludes_dimensional_rows() -> None:
    children = _income().children("GrossProfit")
    assert children["row_id"].tolist() == ["Revenues", "CostOfRevenue"]


def test_children_unknown_row_raises() -> None:
    with pytest.raises(KeyError):
        _income().children("Nope")


# --- projection --------------------------------------------------------------


def test_project_summary_drops_all_dimensional_rows() -> None:
    out = _income().project("summary")
    assert not any("|" in rid for rid in out["row_id"])


def test_project_standard_keeps_non_breakdown_dimensions() -> None:
    ids = _income().project("standard")["row_id"].tolist()
    assert "Revenues|ProductOrServiceAxis=ProductMember" in ids
    assert "Revenues|StatementGeographicalAxis=US" not in ids


def test_project_detailed_keeps_all_rows_with_values() -> None:
    ids = _income().project("detailed")["row_id"].tolist()
    assert "Revenues|StatementGeographicalAxis=US" in ids
    assert len(ids) == len(_income_frame())


def test_project_applies_preferred_sign_but_frame_keeps_raw() -> None:
    statement = _income()
    out = statement.project("detailed")
    cost = out.loc[out["row_id"] == "CostOfRevenue", P1].item()
    revenue = out.loc[out["row_id"] == "Revenues", P1].item()
    assert cost == -40.0
    assert revenue == 100.0  # NaN preferred_sign treated as +1
    raw = statement.frame.loc[statement.frame["row_id"] == "CostOfRevenue", P1]
    assert raw.item() == 40.0


def test_project_slices_periods_and_drops_empty_rows() -> None:
    out = _income().project("detailed", periods=[P2, P3])
    assert list(out.columns) == [*PROJECTION_METADATA_COLUMNS, P2, P3]
    ids = out["row_id"].tolist()
    assert "ResearchAndDevelopmentExpense" not in ids  # only has P1
    assert "SellingGeneralAndAdministrativeExpense" in ids
    assert "IncomeStatementAbstract" in ids  # abstract rows kept as-is


def test_project_unknown_period_raises() -> None:
    with pytest.raises(KeyError):
        _income().project("detailed", periods=["1999-12-31"])


def test_project_columns_are_table_metadata_plus_row_id() -> None:
    out = _income().project("summary")
    meta = [c for c in out.columns if c not in (P1, P2, P3)]
    assert set(meta) - STATEMENT_VIEW_METADATA_COLUMNS == {"row_id"}


# --- immutability ------------------------------------------------------------


def test_insert_returns_new_statement_after_row() -> None:
    base = _income()
    new = base.insert(
        {
            "concept": "DepreciationRnD",
            "label": "Depreciation (R&D)",
            "parent_concept": "OperatingExpenses",
            "weight": 1.0,
            "tags": {"da"},
            "origin": "adjustment:opex_to_capex",
            P1: 2.0,
        },
        after="ResearchAndDevelopmentExpense",
    )
    assert "DepreciationRnD" not in base.frame["row_id"].tolist()
    ids = new.frame["row_id"].tolist()
    assert ids[ids.index("ResearchAndDevelopmentExpense") + 1] == "DepreciationRnD"
    inserted = new.frame.loc[new.frame["row_id"] == "DepreciationRnD"].iloc[0]
    assert inserted["origin"] == "adjustment:opex_to_capex"
    assert inserted["tags"] == ("da",)
    assert inserted[P1] == 2.0
    assert math.isnan(inserted[P2])


def test_insert_appends_by_default_and_requires_origin() -> None:
    base = _income()
    with pytest.raises(ValueError, match="origin"):
        base.insert({"concept": "X", "label": "X"})
    new = base.insert({"concept": "X", "label": "X", "origin": "adjustment:t"})
    assert new.frame["row_id"].iloc[-1] == "X"


def test_insert_rejects_existing_row_id() -> None:
    with pytest.raises(DuplicateRowIdError):
        _income().insert({"concept": "Revenues", "origin": "adjustment:t"})


def test_with_values_returns_new_statement() -> None:
    base = _income()
    new = base.with_values("ResearchAndDevelopmentExpense", {P1: 0.0, P2: 1.5})
    row = new.frame.loc[new.frame["row_id"] == "ResearchAndDevelopmentExpense"]
    assert row[P1].item() == 0.0
    assert row[P2].item() == 1.5
    old = base.frame.loc[base.frame["row_id"] == "ResearchAndDevelopmentExpense"]
    assert old[P1].item() == 10.0
    with pytest.raises(KeyError):
        base.with_values("ResearchAndDevelopmentExpense", {"1999-12-31": 1.0})
    with pytest.raises(KeyError):
        base.with_values("Nope", {P1: 1.0})


# --- StatementSet ------------------------------------------------------------


def _minimal(statement_type: str) -> Statement:
    frame = pd.DataFrame([_row("A", "A", **{P1: 1.0})])
    return Statement(frame, statement_type)  # type: ignore[arg-type]


def test_statement_set_get_and_project() -> None:
    ss = StatementSet(
        income=_income(),
        balance=_minimal("balance"),
        cashflow=_minimal("cashflow"),
        periods=(P1, P2, P3),
    )
    assert ss.get("balance") is ss.balance
    projected = ss.project("summary", periods=[P1])
    assert set(projected) == {"income", "balance", "cashflow"}
    assert list(projected["balance"].columns) == [*PROJECTION_METADATA_COLUMNS, P1]


def test_statement_set_rejects_mismatched_statement_type() -> None:
    with pytest.raises(ValueError):
        StatementSet(
            income=_minimal("balance"),
            balance=_minimal("balance"),
            cashflow=_minimal("cashflow"),
            periods=(P1,),
        )
