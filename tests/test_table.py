"""Tests for column-based table serialization."""

from __future__ import annotations

import pandas as pd
import pytest

from src.models.statement import Statement, get_row_id
from src.models.table import (
    ColumnSpec,
    LinkedGroupSpec,
    Table,
    TableSerializationError,
    statement_table_from_dataframe,
)


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

    assert list(payload.keys()) == ["columns", "linked_groups", "rows"]
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
    projected = Statement(raw, "income").project("detailed", ["2024-12-31"])

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
