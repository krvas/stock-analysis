"""Tests for column-based table serialization."""

from __future__ import annotations

import pandas as pd
import pytest

from src.models.table import statement_table_from_dataframe
from src.models.table import ColumnSpec, LinkedGroupSpec, Table, TableSerializationError


def test_table_serialize_statement_shape() -> None:
    df = pd.DataFrame(
        {
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


def test_table_find_row_id_matches_row_id_col_and_standard_concept() -> None:
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
    # Exact match against row_id_col ("concept").
    assert table.find_row_id("us-gaap_ResearchAndDevelopmentExpense") == (
        "us-gaap_ResearchAndDevelopmentExpense"
    )
    # Exact match against standard_concept.
    assert (
        table.find_row_id("ResearchAndDevelopmentExpenses")
        == "us-gaap_ResearchAndDevelopmentExpense"
    )
    # A key that would have matched under the old unscoped suffix heuristic
    # (it's a suffix of the concept string, but not an exact match against
    # either row_id_col or standard_concept) must now return None rather
    # than silently guessing.
    assert table.find_row_id("ResearchAndDevelopmentExpense") is None


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
    with pytest.raises(TableSerializationError, match="partial Table cannot be serialized"):
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
