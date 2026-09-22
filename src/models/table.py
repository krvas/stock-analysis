"""Column-based table serialization for financial statement views."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import pandas as pd

ColumnKind = Literal["static", "input", "link"]
ColumnDtype = Literal["number", "string"]
LinkedGroupType = Literal["pct_of_base"]
NumberFormat = Literal["financial", "percent", "integer"]

_NUMBER_FORMATS: frozenset[str] = frozenset({"financial", "percent", "integer"})


@dataclass(frozen=True)
class ColumnSpec:
    """Describes one logical column in a serialized table."""

    id: str
    label: str
    kind: ColumnKind
    dtype: ColumnDtype
    format: str | None = None
    linked_group: str | None = None


@dataclass(frozen=True)
class LinkedGroupSpec:
    """Relationship between columns (e.g. percent-of-base inputs)."""

    type: LinkedGroupType
    base_col: str
    pct_col: str
    value_col: str


class TableSerializationError(ValueError):
    """Invalid table configuration or source data for serialization."""


def _validate_column_spec(spec: ColumnSpec) -> None:
    if not spec.id:
        raise TableSerializationError("ColumnSpec.id must be non-empty")
    if spec.kind == "link" and spec.dtype != "string":
        raise TableSerializationError(
            f"Column '{spec.id}': link columns must have dtype 'string'"
        )
    if spec.format is None:
        return
    if spec.dtype == "number":
        if spec.format not in _NUMBER_FORMATS:
            raise TableSerializationError(
                f"Column '{spec.id}': unknown number format '{spec.format}'"
            )
        return
    raise TableSerializationError(
        f"Column '{spec.id}': string columns cannot have a format"
    )


def _cell_value_from_raw(raw: object) -> Any:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if pd.isna(raw):
        return None
    if isinstance(raw, dict) and "text" in raw and "href" in raw:
        return {"text": raw["text"], "href": raw["href"]}
    return raw


class Table:
    """Build a column-schema JSON payload from a DataFrame and column specs."""

    def __init__(
        self,
        df: pd.DataFrame,
        columns: list[ColumnSpec],
        linked_groups: dict[str, LinkedGroupSpec],
        *,
        row_id_col: str,
        level_col: str | None = None,
        parent_id_col: str | None = None,
        label_col: str = "label",
    ) -> None:
        if not row_id_col:
            raise TableSerializationError("row_id_col must be non-empty")

        resolved_level_col = level_col
        if resolved_level_col is None:
            resolved_level_col = "level" if "level" in df.columns else None

        column_ids = [spec.id for spec in columns]
        if len(column_ids) != len(set(column_ids)):
            raise TableSerializationError("Duplicate column ids in columns list")

        for spec in columns:
            _validate_column_spec(spec)
            if spec.linked_group is not None and spec.linked_group not in linked_groups:
                raise TableSerializationError(
                    f"Column '{spec.id}' references unknown linked_group "
                    f"'{spec.linked_group}'"
                )

        column_id_set = set(column_ids)
        for group_name, group in linked_groups.items():
            for ref in (group.base_col, group.pct_col, group.value_col):
                if ref not in column_id_set:
                    raise TableSerializationError(
                        f"linked_groups['{group_name}'] references unknown column '{ref}'"
                    )

        if row_id_col not in df.columns:
            raise TableSerializationError(
                f"row_id_col '{row_id_col}' not found in DataFrame"
            )
        if label_col not in df.columns:
            raise TableSerializationError(
                f"label_col '{label_col}' not found in DataFrame"
            )
        if parent_id_col is not None and parent_id_col not in df.columns:
            raise TableSerializationError(
                f"parent_id_col '{parent_id_col}' not found in DataFrame"
            )

        self._df = df
        self._columns = columns
        self._linked_groups = linked_groups
        self._row_id_col = row_id_col
        self._level_col = resolved_level_col
        self._parent_id_col = parent_id_col
        self._label_col = label_col

    def serialize(self) -> dict[str, Any]:
        """Return the column-based table JSON shape."""
        return {
            "columns": [asdict(spec) for spec in self._columns],
            "linked_groups": {
                name: asdict(spec) for name, spec in self._linked_groups.items()
            },
            "rows": self._serialize_rows(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Alias for :meth:`serialize` (template / API embedding)."""
        return self.serialize()

    def _serialize_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in self._df.to_dict(orient="records"):
            row_id = record.get(self._row_id_col)
            row_id_str = "" if row_id is None or pd.isna(row_id) else str(row_id)

            parent_id: str | None = None
            if self._parent_id_col is not None:
                raw_parent = record.get(self._parent_id_col)
                if raw_parent is not None and not pd.isna(raw_parent):
                    parent_id = str(raw_parent)

            level = 0
            if self._level_col is not None:
                level = int(record.get(self._level_col, 0) or 0)

            cells: dict[str, Any] = {}
            for spec in self._columns:
                if spec.kind == "input" and spec.id not in self._df.columns:
                    cells[spec.id] = None
                elif spec.id in self._df.columns:
                    cells[spec.id] = _cell_value_from_raw(record.get(spec.id))
                else:
                    cells[spec.id] = None

            rows.append(
                {
                    "id": row_id_str,
                    "label": str(record.get(self._label_col, "") or ""),
                    "level": level,
                    "parent_id": parent_id,
                    "cells": cells,
                }
            )
        return rows
