"""Tests for calc-linkbase residuals (:mod:`src.models.calc_residuals`)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.models.calc_residuals import RESIDUAL_COLUMNS, calc_residuals, tagged_residuals
from src.models.statement import Statement
from tests.statement_fixtures import P1, P2, P3, _income, _row, make_statement

# --- calc_residuals ----------------------------------------------------------


def _residual_by(residuals: pd.DataFrame) -> dict[tuple[str, str], float]:
    return {
        (row.row_id, row.period): row.residual
        for row in residuals.itertuples(index=False)
    }


def test_calc_residuals_zero_for_complete_tree_with_negative_weight() -> None:
    # GrossProfit = Revenues - CostOfRevenue (weight -1); the dimensional
    # Revenues rows (60/70 in P1) are excluded from the sum.
    residuals = calc_residuals(_income())

    assert set(residuals["row_id"]) == {"GrossProfit"}
    assert sorted(residuals["period"]) == sorted([P1, P2, P3])
    assert (residuals["residual"] == 0).all()
    assert (residuals["relative"] == 0).all()
    assert (residuals["n_children"] == 2).all()
    p1 = residuals.set_index("period").loc[P1]
    assert (p1["reported"], p1["computed"]) == (60.0, 60.0)


def test_calc_residuals_non_zero_residual_uses_raw_signs() -> None:
    frame = pd.DataFrame(
        [
            _row("Opex", "Opex", **{P1: 30.0}),
            _row("RD", "R&D", parent_concept="Opex", preferred_sign=-1.0, **{P1: 10.0}),
            _row("SGA", "SG&A", parent_concept="Opex", **{P1: 15.0}),
        ]
    )
    residuals = calc_residuals(make_statement(frame, "income"))

    assert len(residuals) == 1
    row = residuals.iloc[0]
    assert row["row_id"] == "Opex"
    assert row["computed"] == 25.0
    assert row["residual"] == 5.0
    assert row["relative"] == pytest.approx(5.0 / 30.0)


def test_calc_residuals_skips_nan_parent_and_zero_fills_nan_children() -> None:
    frame = pd.DataFrame(
        [
            _row("Total", "Total", **{P1: 10.0, P2: None, P3: 7.0}),
            _row("A", "A", parent_concept="Total", **{P1: 4.0, P2: 1.0, P3: None}),
            _row("B", "B", parent_concept="Total", weight=-1.0, **{P1: -6.0}),
        ]
    )
    residuals = calc_residuals(make_statement(frame, "income")).set_index("period")

    assert list(residuals.index) == [P1, P3]
    assert residuals.loc[P1, "residual"] == 0.0
    assert residuals.loc[P1, "n_nan_children"] == 0
    assert residuals.loc[P3, "computed"] == 0.0
    assert residuals.loc[P3, "residual"] == 7.0
    assert residuals.loc[P3, "n_nan_children"] == 2


def test_calc_residuals_zero_reported_relative() -> None:
    frame = pd.DataFrame(
        [
            _row("Total", "Total", **{P1: 0.0, P2: 0.0}),
            _row("A", "A", parent_concept="Total", **{P1: 3.0, P2: 0.0}),
        ]
    )
    residuals = calc_residuals(make_statement(frame, "income")).set_index("period")

    assert residuals.loc[P1, "relative"] == -math.inf
    assert math.isnan(residuals.loc[P2, "relative"])


def test_calc_residuals_excludes_dimensional_children_and_parents() -> None:
    frame = pd.DataFrame(
        [
            _row("Total", "Total", **{P1: 5.0}),
            _row("A", "A", parent_concept="Total", **{P1: 5.0}),
            _row(
                "A",
                "A - Segment",
                parent_concept="Total",
                dimension=True,
                dimension_axis="SegmentAxis",
                dimension_member="X",
                **{P1: 100.0},
            ),
            # A dimensional row whose concept is a calc parent is not checked.
            _row(
                "Total",
                "Total - Segment",
                dimension=True,
                dimension_axis="SegmentAxis",
                dimension_member="X",
                **{P1: 999.0},
            ),
        ]
    )
    residuals = calc_residuals(make_statement(frame, "income"))

    assert _residual_by(residuals) == {("Total", P1): 0.0}


def test_calc_residuals_duplicate_concepts_use_first_row() -> None:
    frame = pd.DataFrame(
        [
            _row("Total", "Total", row_id="Total", **{P1: 5.0}),
            _row("A", "A", parent_concept="Total", row_id="A", **{P1: 5.0}),
            _row("A", "A again", parent_concept="Total", row_id="A#2", **{P1: 50.0}),
            _row("Total", "Total again", row_id="Total#2", **{P1: 500.0}),
        ]
    )
    residuals = calc_residuals(make_statement(frame, "income"))

    assert _residual_by(residuals) == {("Total", P1): 0.0}
    assert residuals["n_children"].tolist() == [1]


def test_calc_residuals_empty_without_calc_tree() -> None:
    frame = pd.DataFrame([_row("A", "A", **{P1: 1.0})])
    residuals = calc_residuals(make_statement(frame, "income"))

    assert residuals.empty
    assert list(residuals.columns) == [
        "row_id",
        "concept",
        "label",
        "period",
        "reported",
        "computed",
        "residual",
        "relative",
        "n_children",
        "n_nan_children",
        "n_missing_children",
    ]


def test_calc_residuals_counts_missing_children() -> None:
    # The calc tree has a child (C) the statement does not present.
    frame = pd.DataFrame(
        [
            _row("Total", "Total", **{P1: 12.0}),
            _row("A", "A", parent_concept="Total", **{P1: 10.0}),
        ]
    )
    edges = pd.DataFrame(
        {
            "period": [P1, P1],
            "concept": ["A", "C"],
            "parent_concept": ["Total", "Total"],
            "weight": [1.0, 1.0],
        }
    )
    residuals = calc_residuals(Statement(frame, "income", calc_edges=edges))

    row = residuals.iloc[0]
    assert row["computed"] == 10.0
    assert row["residual"] == 2.0
    assert row["n_children"] == 1
    assert row["n_missing_children"] == 1


def test_calc_residuals_use_each_periods_own_tree() -> None:
    # P1's filing: Total = A - B. P2's (older) filing: Total = A + C, and B
    # is not in its tree. The frame's own columns (newest tree) are ignored.
    frame = pd.DataFrame(
        [
            _row("Total", "Total", **{P1: 6.0, P2: 9.0}),
            _row("A", "A", parent_concept="Total", **{P1: 10.0, P2: 5.0}),
            _row("B", "B", parent_concept="Total", weight=-1.0, **{P1: 4.0, P2: 7.0}),
            _row("C", "C", **{P1: 1.0, P2: 4.0}),
        ]
    )
    edges = pd.DataFrame(
        {
            "period": [P1, P1, P2, P2],
            "concept": ["A", "B", "A", "C"],
            "parent_concept": ["Total", "Total", "Total", "Total"],
            "weight": [1.0, -1.0, 1.0, 1.0],
        }
    )
    residuals = calc_residuals(Statement(frame, "income", calc_edges=edges))

    assert _residual_by(residuals) == {("Total", P1): 0.0, ("Total", P2): 0.0}
    assert residuals["period"].tolist() == [P1, P2]
    assert residuals["computed"].tolist() == [6.0, 9.0]
    # Applying the newest tree to P2 would have given 5 - 7 = -2.
    newest = calc_residuals(make_statement(frame, "income")).set_index("period")
    assert newest.loc[P2, "residual"] == 11.0


# --- tagged_residuals --------------------------------------------------------


def test_tagged_residuals_prefixes_and_concatenates_statements() -> None:
    frame = pd.DataFrame(
        [
            _row("Opex", "Opex", **{P1: 30.0}),
            _row("RD", "R&D", parent_concept="Opex", **{P1: 10.0}),
            _row("SGA", "SG&A", parent_concept="Opex", **{P1: 15.0}),
        ]
    )
    income = make_statement(frame, "income")

    tagged = tagged_residuals(
        {"income": income, "balance": income}, ticker="AAA", period_type="annual"
    )

    assert list(tagged.columns) == [
        "ticker",
        "period_type",
        "statement",
        *RESIDUAL_COLUMNS,
    ]
    assert tagged["statement"].tolist() == ["income", "balance"]
    assert set(tagged["ticker"]) == {"AAA"}
    assert set(tagged["period_type"]) == {"annual"}
    assert tagged["residual"].tolist() == [5.0, 5.0]


def test_tagged_residuals_empty_keeps_columns() -> None:
    tagged = tagged_residuals({}, ticker="AAA", period_type="annual")

    assert tagged.empty
    assert list(tagged.columns) == [
        "ticker",
        "period_type",
        "statement",
        *RESIDUAL_COLUMNS,
    ]
