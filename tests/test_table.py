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
