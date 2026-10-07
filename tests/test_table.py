"""Tests for column-based table serialization."""

from __future__ import annotations

import pandas as pd
import pytest

from src.models.statement import Statement, get_row_id
from src.models.table import (
    CalculatedCellSpec,
    ColumnSpec,
    LinkedGroupSpec,
    Table,
    TableSerializationError,
    statement_table_from_dataframe,
)
from tests.statement_fixtures import derived_calc_edges


def test_table_serialize_statement_shape() -> None:
    df = pd.DataFrame(
        {
            "row_id": ["c1", "c2"],
            "concept": ["c1", "c2"],
            "label": ["Revenue", "Total revenue"],
            "level": [0, 0],
            "is_total": [False, True],
            "2024-12-31": [100.0, 100.0],
            "2023-12-31": [90.0, 90.0],
        }
    )
    payload = statement_table_from_dataframe(df).serialize()

    assert list(payload.keys()) == [
        "columns",
        "linked_groups",
        "rows",
        "calculated_cells",
        "no_input_cells",
    ]
    assert payload["calculated_cells"] == []
    assert payload["no_input_cells"] == []
    assert "origin" not in payload["rows"][0]
    assert len(payload["columns"]) == 2
    assert payload["columns"][0]["kind"] == "static"
    assert payload["columns"][0]["format"] == "financial"
    assert payload["rows"][0]["id"] == "c1"
    assert payload["rows"][0]["cells"]["2024-12-31"] == 100.0
    assert payload["rows"][1]["is_total"] is True


def test_statement_table_keys_rows_by_row_id() -> None:
    raw = pd.DataFrame(
        {
            "concept": ["us-gaap_Revenues", "us-gaap_Revenues", "us-gaap_Revenues"],
            "label": ["Revenue", "Products", "Services"],
            "level": [0, 1, 1],
            "dimension": [False, True, True],
            "is_breakdown": [False, True, True],
            "dimension_axis": [
                None,
                "srt:ProductOrServiceAxis",
                "srt:ProductOrServiceAxis",
            ],
            "dimension_member": [
                None,
                "us-gaap_ProductMember",
                "us-gaap_ServiceMember",
            ],
            "2024-12-31": [100.0, 60.0, 40.0],
        }
    )
    projected = Statement(raw, "income", derived_calc_edges(raw)).project(
        "detailed", ["2024-12-31"]
    )

    rows = statement_table_from_dataframe(projected).serialize()["rows"]

    ids = [row["id"] for row in rows]
    assert ids == [get_row_id(record) for _, record in raw.iterrows()]
    assert ids == [
        "us-gaap_Revenues",
        "us-gaap_Revenues|ProductOrServiceAxis=us-gaap_ProductMember",
        "us-gaap_Revenues|ProductOrServiceAxis=us-gaap_ServiceMember",
    ]
    assert [row["cells"]["2024-12-31"] for row in rows] == [100.0, 60.0, 40.0]


def test_statement_table_requires_row_id_column() -> None:
    df = pd.DataFrame({"concept": ["c1"], "label": ["Revenue"], "2024": [1.0]})
    with pytest.raises(TableSerializationError, match="row_id_col 'row_id'"):
        statement_table_from_dataframe(df)


def test_table_rejects_unknown_linked_group_column() -> None:
    df = pd.DataFrame({"concept": ["a"], "label": ["A"], "x": [1]})
    columns = [
        ColumnSpec(id="x", label="X", kind="static", dtype="number"),
        ColumnSpec(
            id="pct",
            label="%",
            kind="input",
            dtype="number",
            format="percent",
            linked_group="g1",
        ),
    ]
    with pytest.raises(TableSerializationError, match="unknown column 'missing'"):
        Table(
            df,
            columns,
            {
                "g1": LinkedGroupSpec(
                    type="pct_of_base",
                    base_col="x",
                    pct_col="pct",
                    value_col="missing",
                )
            },
            row_id_col="concept",
        )


def test_table_find_row_id_exact_match_on_row_id_col_only() -> None:
    df = pd.DataFrame(
        {
            "concept": ["us-gaap_ResearchAndDevelopmentExpense"],
            "standard_concept": ["ResearchAndDevelopmentExpenses"],
            "label": ["R&D"],
        }
    )
    table = Table(
        df,
        [ColumnSpec(id="x", label="X", kind="input", dtype="string")],
        {},
        row_id_col="concept",
    )
    assert table.find_row_id("us-gaap_ResearchAndDevelopmentExpense") == (
        "us-gaap_ResearchAndDevelopmentExpense"
    )
    assert table.find_row_id("  us-gaap_ResearchAndDevelopmentExpense ") == (
        "us-gaap_ResearchAndDevelopmentExpense"
    )
    # Other columns are never consulted, and there is no fuzzy/suffix match.
    assert table.find_row_id("ResearchAndDevelopmentExpenses") is None
    assert table.find_row_id("ResearchAndDevelopmentExpense") is None
    assert table.find_row_id("") is None


def test_table_find_row_id_matches_any_row_id_col() -> None:
    df = pd.DataFrame(
        {
            "concept": ["us-gaap_ResearchAndDevelopmentExpense"],
            "standard_concept": ["ResearchAndDevelopmentExpenses"],
            "label": ["R&D"],
        }
    )
    table = Table(
        df,
        [ColumnSpec(id="x", label="X", kind="input", dtype="string")],
        {},
        row_id_col="standard_concept",
    )
    assert (
        table.find_row_id("ResearchAndDevelopmentExpenses")
        == "ResearchAndDevelopmentExpenses"
    )
    assert table.find_row_id("us-gaap_ResearchAndDevelopmentExpense") is None


def test_table_set_cell_adds_column_and_updates_row() -> None:
    df = pd.DataFrame({"concept": ["a", "b"], "label": ["A", "B"], "2024": [1.0, 2.0]})
    table = Table(
        df,
        [
            ColumnSpec(id="2024", label="2024", kind="static", dtype="number"),
            ColumnSpec(id="note", label="Note", kind="input", dtype="string"),
        ],
        {},
        row_id_col="concept",
    )
    table.set_cell("note", "b", "saved")
    row = table.serialize()["rows"][1]
    assert row["cells"]["note"] == "saved"
    assert table.serialize()["rows"][0]["cells"]["note"] is None


def test_table_set_cell_unknown_row_raises() -> None:
    df = pd.DataFrame({"concept": ["a"], "label": ["A"]})
    table = Table(
        df,
        [ColumnSpec(id="x", label="X", kind="input", dtype="string")],
        {},
        row_id_col="concept",
    )
    with pytest.raises(TableSerializationError, match="row id 'missing'"):
        table.set_cell("x", "missing", "value")


def test_table_from_rows() -> None:
    columns = [
        ColumnSpec(id="note", label="Note", kind="input", dtype="string"),
        ColumnSpec(id="amount", label="Amount", kind="input", dtype="number"),
    ]
    rows = [
        {"id": "r1", "cells": {"note": "first", "amount": 1.0}},
        {"id": "r2", "cells": {"note": "second", "amount": 2.0}},
        {"id": "r3", "cells": {"note": "third", "amount": 3.0}},
    ]
    table = Table.from_rows(rows, columns)

    assert table.get_cell("r1", "note") == "first"
    assert table.get_cell("r1", "amount") == 1.0
    assert table.get_cell("r2", "note") == "second"
    assert table.get_cell("r3", "amount") == 3.0


def test_table_from_rows_missing_id_raises() -> None:
    columns = [ColumnSpec(id="note", label="Note", kind="input", dtype="string")]
    rows = [{"cells": {"note": "no id here"}}]
    with pytest.raises(TableSerializationError, match="missing required 'id'"):
        Table.from_rows(rows, columns)


def test_table_from_rows_duplicate_column_ids_raises() -> None:
    columns = [
        ColumnSpec(id="note", label="Note", kind="input", dtype="string"),
        ColumnSpec(id="note", label="Note2", kind="input", dtype="string"),
    ]
    rows = [{"id": "r1", "cells": {"note": "x"}}]
    with pytest.raises(TableSerializationError, match="Duplicate column ids"):
        Table.from_rows(rows, columns)


def test_table_get_cell_unknown_row_raises() -> None:
    columns = [ColumnSpec(id="note", label="Note", kind="input", dtype="string")]
    table = Table.from_rows([{"id": "r1", "cells": {"note": "x"}}], columns)
    with pytest.raises(TableSerializationError, match="row id 'missing'"):
        table.get_cell("missing", "note")


def test_table_get_cell_unknown_column_raises() -> None:
    columns = [ColumnSpec(id="note", label="Note", kind="input", dtype="string")]
    table = Table.from_rows([{"id": "r1", "cells": {"note": "x"}}], columns)
    with pytest.raises(TableSerializationError, match="column 'missing' not found"):
        table.get_cell("r1", "missing")


def test_table_from_rows_serialize_raises() -> None:
    columns = [ColumnSpec(id="note", label="Note", kind="input", dtype="string")]
    table = Table.from_rows([{"id": "r1", "cells": {"note": "x"}}], columns)
    with pytest.raises(
        TableSerializationError, match="partial Table cannot be serialized"
    ):
        table.serialize()


def test_table_input_columns_without_dataframe_column() -> None:
    df = pd.DataFrame({"concept": ["a"], "label": ["A"], "2024": [5.0]})
    table = Table(
        df,
        [
            ColumnSpec(id="2024", label="2024", kind="static", dtype="number"),
            ColumnSpec(id="note", label="Note", kind="input", dtype="string"),
        ],
        {},
        row_id_col="concept",
    )
    row = table.serialize()["rows"][0]
    assert row["cells"]["note"] is None
    assert row["cells"]["2024"] == 5.0


def _calc_table_parts() -> tuple[pd.DataFrame, list[ColumnSpec]]:
    df = pd.DataFrame(
        {
            "row_id": ["r1", "r2"],
            "label": ["A", "B"],
            "amount": [100.0, 50.0],
            "years": [None, 5.0],
        }
    )
    columns = [
        ColumnSpec(id="amount", label="Amount", kind="static", dtype="number"),
        ColumnSpec(id="years", label="Years", kind="input", dtype="number"),
    ]
    return df, columns


def test_table_serializes_calculated_cells() -> None:
    df, columns = _calc_table_parts()
    expr = {
        "op": "add",
        "args": [
            {"cell": ["r1", "amount"]},
            {"op": "mul", "args": [{"const": -1}, {"cell": ["r2", "years"]}]},
        ],
    }
    table = Table(
        df,
        columns,
        linked_groups={},
        row_id_col="row_id",
        calculated_cells=[CalculatedCellSpec(row_id="r2", col_id="amount", expr=expr)],
    )

    payload = table.serialize()

    assert payload["calculated_cells"] == [
        {"row_id": "r2", "col_id": "amount", "expr": expr}
    ]
    assert payload["rows"][0]["cells"]["amount"] == 100.0


@pytest.mark.parametrize(
    ("row_id", "col_id", "expr"),
    [
        ("missing", "amount", {"const": 1}),
        ("r1", "missing", {"const": 1}),
        ("r1", "amount", {"cell": ["missing", "amount"]}),
        ("r1", "amount", {"cell": ["r1", "missing"]}),
        ("r1", "amount", {"cell": ["r1"]}),
        ("r1", "amount", {"const": "1"}),
        ("r1", "amount", {"const": True}),
        ("r1", "amount", {"op": "sub", "args": [{"const": 1}]}),
        ("r1", "amount", {"op": "add", "args": []}),
        ("r1", "amount", {"op": "add", "args": [{"bogus": 1}]}),
        ("r1", "amount", {}),
    ],
)
def test_table_rejects_invalid_calculated_cell(
    row_id: str, col_id: str, expr: dict
) -> None:
    df, columns = _calc_table_parts()
    with pytest.raises(TableSerializationError):
        Table(
            df,
            columns,
            linked_groups={},
            row_id_col="row_id",
            calculated_cells=[
                CalculatedCellSpec(row_id=row_id, col_id=col_id, expr=expr)
            ],
        )


def test_statement_table_passes_row_origin_through() -> None:
    df = pd.DataFrame(
        {
            "row_id": ["c1", "c2"],
            "concept": ["c1", "c2"],
            "label": ["Revenue", "Capitalized R&D"],
            "level": [0, 0],
            "origin": ["reported", "adjustment:opex_to_capex"],
            "2024-12-31": [100.0, 10.0],
        }
    )

    payload = statement_table_from_dataframe(df).serialize()

    assert [col["id"] for col in payload["columns"]] == ["2024-12-31"]
    assert [row["origin"] for row in payload["rows"]] == [
        "reported",
        "adjustment:opex_to_capex",
    ]


def test_table_serializes_no_input_cells() -> None:
    df, columns = _calc_table_parts()
    table = Table(
        df,
        columns,
        linked_groups={},
        row_id_col="row_id",
        no_input_cells=[("r1", "years")],
    )

    assert table.serialize()["no_input_cells"] == [["r1", "years"]]


@pytest.mark.parametrize(
    "cell", [("missing", "years"), ("r1", "missing"), ("r1", "amount")]
)
def test_table_rejects_invalid_no_input_cells(cell: tuple[str, str]) -> None:
    df, columns = _calc_table_parts()
    with pytest.raises(TableSerializationError):
        Table(
            df,
            columns,
            linked_groups={},
            row_id_col="row_id",
            no_input_cells=[cell],
        )
