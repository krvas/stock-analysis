"""Tests for the Statement / StatementSet domain model."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.models.statement import (
    CALC_EDGE_COLUMNS,
    PROJECTION_METADATA_COLUMNS,
    DuplicateRowIdError,
    Statement,
    StatementSet,
    format_dimension_key,
    get_row_id,
    is_total_label,
)
from src.models.table import STATEMENT_VIEW_METADATA_COLUMNS
from tests.statement_fixtures import (
    P1,
    P2,
    P3,
    _income,
    _income_frame,
    _row,
    derived_calc_edges,
    make_statement,
)

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


def test_get_row_id_uses_every_axis_from_dimension_key_sorted_by_axis() -> None:
    row = {
        "concept": "Rev",
        "dimension_axis": "srt:ConsolidationItemsAxis",
        "dimension_member": "us-gaap_OperatingSegmentsMember",
        "dimension_key": format_dimension_key(
            [
                ("srt:ConsolidationItemsAxis", "us-gaap_OperatingSegmentsMember"),
                ("us-gaap:StatementBusinessSegmentsAxis", "aapl_AmericasMember"),
            ]
        ),
    }
    other = {
        **row,
        "dimension_key": format_dimension_key(
            [
                ("srt:ConsolidationItemsAxis", "us-gaap_OperatingSegmentsMember"),
                ("us-gaap:StatementBusinessSegmentsAxis", "aapl_EuropeMember"),
            ]
        ),
    }
    assert get_row_id(row) == (
        "Rev|ConsolidationItemsAxis=us-gaap_OperatingSegmentsMember"
        "|StatementBusinessSegmentsAxis=aapl_AmericasMember"
    )
    assert get_row_id(row) != get_row_id(other)
    reordered = {
        **row,
        "dimension_key": format_dimension_key(
            [
                ("us-gaap:StatementBusinessSegmentsAxis", "aapl_AmericasMember"),
                ("srt:ConsolidationItemsAxis", "us-gaap_OperatingSegmentsMember"),
            ]
        ),
    }
    assert get_row_id(reordered) == get_row_id(row)


def test_get_row_id_strips_axis_namespace_but_not_member() -> None:
    old = {
        "concept": "Rev",
        "dimension_axis": "us-gaap:ConsolidationItemsAxis",
        "dimension_member": "us-gaap_CorporateNonSegmentMember",
    }
    new = {**old, "dimension_axis": "srt:ConsolidationItemsAxis"}
    underscore = {**old, "dimension_axis": "srt_ConsolidationItemsAxis"}
    expected = "Rev|ConsolidationItemsAxis=us-gaap_CorporateNonSegmentMember"
    assert get_row_id(old) == get_row_id(new) == get_row_id(underscore) == expected
    assert get_row_id({**old, "dimension_member": "srt_CorporateNonSegmentMember"}) != (
        expected
    )


def test_get_row_id_single_axis_key_matches_primary_fallback() -> None:
    row = {"concept": "Rev", "dimension_axis": "srt:A", "dimension_member": "x_M"}
    keyed = {**row, "dimension_key": format_dimension_key([("srt:A", "x_M")])}
    assert get_row_id(row) == get_row_id(keyed) == "Rev|A=x_M"
    assert format_dimension_key([]) is None


def test_get_row_id_occurrence_suffix() -> None:
    row = {"concept": "Cash", "dimension_axis": "A", "dimension_member": "M"}
    assert get_row_id({"concept": "Cash"}, occurrence=1) == "Cash"
    assert get_row_id({"concept": "Cash"}, occurrence=2) == "Cash#2"
    assert get_row_id(row, occurrence=3) == "Cash|A=M#3"
    with pytest.raises(ValueError):
        get_row_id({"concept": "Cash"}, occurrence=0)


def test_is_total_label() -> None:
    assert is_total_label("Total assets")
    assert is_total_label("Assets, TOTAL")
    assert not is_total_label("Subtotaled items")
    assert not is_total_label(None)


# --- construction ------------------------------------------------------------


def test_constructor_fills_added_columns_without_mutating_input() -> None:
    frame = _income_frame()
    before = frame.copy()
    statement = make_statement(frame, "income")

    pd.testing.assert_frame_equal(frame, before)
    df = statement.frame
    assert df["row_id"].tolist()[2] == "Revenues|ProductOrServiceAxis=ProductMember"
    assert (df["origin"] == "reported").all()
    assert all(tags == () for tags in df["tags"])
    assert df.loc[df["concept"] == "GrossProfit", "is_total"].item()
    assert not df.loc[df["concept"] == "Revenues", "is_total"].iloc[0]
    # in_standard defaults to "not dimension or not is_breakdown".
    assert df["in_standard"].tolist() == [
        True,
        True,
        True,
        False,
        True,
        True,
        True,
        True,
    ]
    assert statement.periods == [P1, P2, P3]


def test_constructor_fills_missing_in_standard_cells_with_default() -> None:
    frame = _income_frame()
    frame["in_standard"] = [True, True, False, None, None, True, True, True]
    df = make_statement(frame, "income").frame
    assert df["in_standard"].dtype == bool
    # Stored flags win; missing cells get the default (US is a breakdown).
    assert df["in_standard"].tolist() == [
        True,
        True,
        False,
        False,
        True,
        True,
        True,
        True,
    ]


def test_constructor_normalizes_parquet_style_tags() -> None:
    frame = _income_frame()
    frame["tags"] = [None] * (len(frame) - 1) + [["da", "b"]]
    statement = make_statement(frame, "income")
    assert statement.frame["tags"].iloc[-1] == ("b", "da")
    assert statement.frame["tags"].iloc[0] == ()


def test_constructor_raises_on_duplicate_row_ids() -> None:
    frame = pd.DataFrame(
        [_row("Revenues", "Revenue"), _row("Revenues", "Revenue again")]
    )
    with pytest.raises(DuplicateRowIdError, match="Revenues"):
        make_statement(frame, "income")


def test_constructor_rejects_unknown_statement_type() -> None:
    with pytest.raises(ValueError):
        make_statement(_income_frame(), "equity")  # type: ignore[arg-type]


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


def test_children_via_calc_edges_excludes_dimensional_rows() -> None:
    children = _income().children("GrossProfit", P1)
    assert children["row_id"].tolist() == ["Revenues", "CostOfRevenue"]
    assert children["weight"].tolist() == [1.0, -1.0]


def test_children_use_the_periods_own_tree_and_edge_weight() -> None:
    edges = pd.DataFrame(
        {
            "period": [P1, P1, P2],
            "concept": ["Revenues", "CostOfRevenue", "CostOfRevenue"],
            "parent_concept": ["GrossProfit", "GrossProfit", "GrossProfit"],
            # P2's filing weighs CostOfRevenue +1 (frame column says -1).
            "weight": [1.0, -1.0, 1.0],
        }
    )
    statement = Statement(_income_frame(), "income", calc_edges=edges)

    p2 = statement.children("GrossProfit", P2)
    assert p2["row_id"].tolist() == ["CostOfRevenue"]
    assert p2["weight"].tolist() == [1.0]
    assert statement.children("GrossProfit", P3).empty


@pytest.mark.parametrize(("row_id", "period"), [("Nope", P1), ("GrossProfit", "x")])
def test_children_unknown_row_or_period_raises(row_id: str, period: str) -> None:
    with pytest.raises(KeyError):
        _income().children(row_id, period)


# --- projection --------------------------------------------------------------


def test_project_summary_drops_all_dimensional_rows() -> None:
    out = _income().project("summary")
    assert not any("|" in rid for rid in out["row_id"])


def test_project_standard_keeps_non_breakdown_dimensions() -> None:
    ids = _income().project("standard")["row_id"].tolist()
    assert "Revenues|ProductOrServiceAxis=ProductMember" in ids
    assert "Revenues|StatementGeographicalAxis=US" not in ids


def test_project_standard_filters_on_stored_in_standard() -> None:
    """A non-breakdown dimensional row whose member edgartools' standard view
    drops (``in_standard`` False) is hidden in standard, shown in detailed."""
    frame = _income_frame()
    frame["in_standard"] = [True, True, False, False, True, True, True, True]
    statement = make_statement(frame, "income")
    product = "Revenues|ProductOrServiceAxis=ProductMember"
    assert product not in statement.project("standard")["row_id"].tolist()
    assert product in statement.project("detailed")["row_id"].tolist()


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
    assert "IncomeStatementAbstract" in ids  # has kept descendants


def test_project_keeps_only_abstracts_with_kept_descendants() -> None:
    rows = [
        _row("Top", "Top", abstract=True, level=0),
        _row("Section", "Section", abstract=True, parent_abstract_concept="Top"),
        _row("Leaf", "Leaf", parent_abstract_concept="Section", **{P1: 1.0}),
        _row("Empty", "Empty", abstract=True, parent_abstract_concept="Top"),
        _row("Dead", "Dead", parent_abstract_concept="Empty", **{P2: 2.0}),
        _row("Orphan", "Orphan header", abstract=True),
    ]
    statement = make_statement(pd.DataFrame(rows), "income")

    # Nested ancestors of a kept row survive; headers over empty rows do not.
    assert statement.project("detailed", periods=[P1])["row_id"].tolist() == [
        "Top",
        "Section",
        "Leaf",
    ]
    assert statement.project("detailed", periods=[P2])["row_id"].tolist() == [
        "Top",
        "Empty",
        "Dead",
    ]


def test_project_drops_abstract_whose_only_descendants_are_filtered_by_view() -> None:
    rows = [
        _row("Geo", "By geography", abstract=True),
        _row(
            "Rev",
            "US",
            dimension=True,
            is_breakdown=True,
            dimension_axis="GeoAxis",
            dimension_member="US",
            parent_abstract_concept="Geo",
            **{P1: 1.0},
        ),
    ]
    statement = make_statement(pd.DataFrame(rows), "income")
    assert statement.project("summary").empty
    assert statement.project("detailed")["row_id"].tolist() == [
        "Geo",
        "Rev|GeoAxis=US",
    ]


def test_project_unknown_period_raises() -> None:
    with pytest.raises(KeyError):
        _income().project("detailed", periods=["1999-12-31"])


def test_project_columns_are_table_metadata_plus_row_id() -> None:
    out = _income().project("summary")
    meta = [c for c in out.columns if c not in (P1, P2, P3)]
    assert "row_id" in meta
    assert set(meta) <= STATEMENT_VIEW_METADATA_COLUMNS


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
    assert inserted["in_standard"]  # non-dimensional inserted rows default to True
    assert "DepreciationRnD" in new.project("standard")["row_id"].tolist()
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


# --- calc_edges --------------------------------------------------------------


def _edge_set(edges: pd.DataFrame, period: str) -> set[tuple[str, str, float]]:
    rows = edges[edges["period"] == period]
    return set(
        zip(rows["concept"], rows["parent_concept"], rows["weight"], strict=True)
    )


def _per_period_edges() -> pd.DataFrame:
    """P1 and P2 from a filing where CostOfRevenue rolls into GrossProfit; P3
    from an older one where it rolled into OperatingIncome."""
    return pd.DataFrame(
        {
            "period": [P1, P1, P2, P3],
            "concept": ["Revenues", "CostOfRevenue", "Revenues", "CostOfRevenue"],
            "parent_concept": [
                "GrossProfit",
                "GrossProfit",
                "GrossProfit",
                "OperatingIncome",
            ],
            "weight": [1.0, -1.0, 1.0, -1.0],
        }
    )


def test_derived_calc_edges_broadcasts_frame_tree_to_every_period() -> None:
    frame = _income_frame()
    # A NaN-weight child carries no edge; a duplicated concept keeps its first.
    frame.loc[frame["concept"] == "ResearchAndDevelopmentExpense", "parent_concept"] = (
        "OperatingExpenses"
    )
    frame.loc[frame["concept"] == "ResearchAndDevelopmentExpense", "weight"] = None
    extra = _row("CostOfRevenue", "Cost again", parent_concept="Other", weight=1.0)
    frame = pd.concat([frame, pd.DataFrame([extra])], ignore_index=True)
    frame["row_id"] = [
        *(get_row_id(row) for _, row in frame.iloc[:-1].iterrows()),
        "CostOfRevenue#2",
    ]

    edges = derived_calc_edges(frame)

    assert list(edges.columns) == list(CALC_EDGE_COLUMNS)
    expected = {
        ("Revenues", "GrossProfit", 1.0),
        ("CostOfRevenue", "GrossProfit", -1.0),
    }
    for period in (P1, P2, P3):
        assert _edge_set(edges, period) == expected
    assert len(edges) == 3 * len(expected)


def test_derived_calc_edges_empty_without_parent_column() -> None:
    frame = _income_frame().drop(columns=["parent_concept"])
    edges = derived_calc_edges(frame)
    assert edges.empty
    assert list(edges.columns) == list(CALC_EDGE_COLUMNS)


def test_calc_edges_given_are_kept_per_period() -> None:
    statement = Statement(_income_frame(), "income", calc_edges=_per_period_edges())
    assert _edge_set(statement.calc_edges, P3) == {
        ("CostOfRevenue", "OperatingIncome", -1.0)
    }
    assert _edge_set(statement.calc_edges, P2) == {("Revenues", "GrossProfit", 1.0)}
    # The frame's own (newest-filing) columns are untouched metadata.
    cost = statement.find(concept="CostOfRevenue").iloc[0]
    assert cost["parent_concept"] == "GrossProfit"


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda e: e.drop(columns=["weight"]), "missing column"),
        (lambda e: e.assign(weight=[1.0, None, 1.0, -1.0]), "missing 'weight'"),
        (
            lambda e: e.assign(parent_concept=["GrossProfit", None, "G", "O"]),
            "missing 'parent_concept'",
        ),
        (lambda e: e.assign(period=[P1, P1, P2, "1999-12-31"]), "unknown period"),
        (
            lambda e: e.assign(concept=["Revenues", "Revenues", "Revenues", "C"]),
            "more than one parent",
        ),
    ],
    ids=["no-weight-column", "nan-weight", "nan-parent", "unknown-period", "dup"],
)
def test_calc_edges_validation(change, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Statement(_income_frame(), "income", calc_edges=change(_per_period_edges()))


def test_calc_edges_carried_by_with_values_and_insert() -> None:
    base = Statement(_income_frame(), "income", calc_edges=_per_period_edges())
    changed = base.with_values("ResearchAndDevelopmentExpense", {P1: 0.0})
    inserted = base.insert(
        {
            "concept": "DepreciationRnD",
            "parent_concept": "OperatingExpenses",
            "origin": "adjustment:opex_to_capex",
        }
    )
    for statement in (changed, inserted):
        pd.testing.assert_frame_equal(statement.calc_edges, base.calc_edges)
    # Inserted rows get no edges yet (adjustments engine work).
    assert "DepreciationRnD" not in set(inserted.calc_edges["concept"])


# --- StatementSet ------------------------------------------------------------


def _minimal(statement_type: str) -> Statement:
    frame = pd.DataFrame([_row("A", "A", **{P1: 1.0})])
    return make_statement(frame, statement_type)  # type: ignore[arg-type]


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
