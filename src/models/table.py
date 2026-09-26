"""Column-based table serialization for financial statement views."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import pandas as pd

ColumnKind = Literal["static", "input", "link"]
ColumnDtype = Literal["number", "string", "boolean"]
LinkedGroupType = Literal["pct_of_base"]
NumberFormat = Literal["financial", "percent", "integer"]

_NUMBER_FORMATS: frozenset[str] = frozenset({"financial", "percent", "integer"})

STATEMENT_VIEW_METADATA_COLUMNS: frozenset[str] = frozenset(
    {
        "label",
        "concept",
        "standard_concept",
        "preferred_sign",
        "level",
        "is_total",
        "is_abstract",
    }
)


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
        f"Column '{spec.id}': only number columns may have a format"
    )


def period_columns(
    df: pd.DataFrame,
    metadata_columns: frozenset[str] = STATEMENT_VIEW_METADATA_COLUMNS,
) -> list[str]:
    return [col for col in df.columns if col not in metadata_columns]


def period_column_specs(df: pd.DataFrame) -> list[ColumnSpec]:
    """Column specs for multi-period numeric columns in a statement view DataFrame."""
    return [
        ColumnSpec(
            id=period,
            label=period,
            kind="static",
            dtype="number",
            format="financial",
        )
        for period in period_columns(df)
    ]


def statement_table_from_dataframe(df: pd.DataFrame) -> Table:
    """Build a :class:`Table` for a standard multi-period statement view."""
    return Table(
        df,
        period_column_specs(df),
        linked_groups={},
        row_id_col="concept",
        level_col="level",
        parent_id_col=None,
        is_total_col="is_total",
    )


def _cell_value_from_raw(raw: object) -> Any:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float, str)):
        if isinstance(raw, float) and pd.isna(raw):
            return None
        return raw
    if hasattr(raw, "item") and not isinstance(raw, (bytes, dict, list, tuple)):
        try:
            return _cell_value_from_raw(raw.item())
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
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
        label_col: str | None = "label",
        is_total_col: str | None = "is_total",
        partial: bool = False,
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
        if not partial and label_col is not None and label_col not in df.columns:
            raise TableSerializationError(
                f"label_col '{label_col}' not found in DataFrame"
            )
        if parent_id_col is not None and parent_id_col not in df.columns:
            raise TableSerializationError(
                f"parent_id_col '{parent_id_col}' not found in DataFrame"
            )

        resolved_is_total_col = is_total_col
        if resolved_is_total_col is not None and resolved_is_total_col not in df.columns:
            resolved_is_total_col = None

        self._df = df
        self._columns = columns
        self._linked_groups = linked_groups
        self._row_id_col = row_id_col
        self._level_col = resolved_level_col
        self._parent_id_col = parent_id_col
        self._label_col = label_col
        self._is_total_col = resolved_is_total_col
        self._partial = partial

    def serialize(self) -> dict[str, Any]:
        """Return the column-based table JSON shape."""
        if self._partial:
            raise TableSerializationError("partial Table cannot be serialized")
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

    def find_row_id(self, base_concept: str) -> str | None:
        """Map a stored ``base_concept`` key to this table's ``row_id_col`` value."""
        key = str(base_concept).strip()
        if not key:
            return None

        concepts = self._df[self._row_id_col].astype(str)
        if key in concepts.values:
            return key

        if "standard_concept" in self._df.columns:
            standard = self._df["standard_concept"].astype(str)
            match = standard == key
            if match.any():
                return str(self._df.loc[match, self._row_id_col].iloc[0])

        return None

    def set_cell(self, column_id: str, row_id: str, value: Any) -> None:
        """Set ``column_id`` for the row identified by ``row_id``.

        If ``column_id`` is not yet a DataFrame column, it is added and
        initialized with null values for every row.
        """
        if column_id not in self._df.columns:
            self._df[column_id] = pd.NA

        row_key = str(row_id)
        mask = self._df[self._row_id_col].astype(str) == row_key
        if not mask.any():
            raise TableSerializationError(
                f"row id '{row_id}' not found in column '{self._row_id_col}'"
            )
        self._df.loc[mask, column_id] = value

    def get_cell(self, row_id: str, column_id: str) -> Any:
        """Return the normalized value of ``column_id`` for the row ``row_id``."""
        row_key = str(row_id)
        mask = self._df[self._row_id_col].astype(str) == row_key
        if not mask.any():
            raise TableSerializationError(
                f"row id '{row_id}' not found in column '{self._row_id_col}'"
            )
        if column_id not in self._df.columns:
            raise TableSerializationError(
                f"column '{column_id}' not found in DataFrame"
            )
        raw = self._df.loc[mask, column_id].iloc[0]
        return _cell_value_from_raw(raw)

    @classmethod
    def from_rows(
        cls,
        rows: list[dict[str, Any]],
        columns: list[ColumnSpec],
        *,
        row_id_col: str = "id",
    ) -> Table:
        """Build a partial :class:`Table` from deserialized ``{id, cells}`` rows.

        This matches the wire shape produced by the frontend's
        ``TableModel.serialize()``. The resulting table has no label/level/
        metadata and can only be read via :meth:`get_cell` or written via
        :meth:`set_cell` — it cannot be serialized.
        """
        if not isinstance(rows, list):
            raise TableSerializationError("rows must be a list")

        records: list[dict[str, Any]] = []
        for entry in rows:
            if not isinstance(entry, dict):
                raise TableSerializationError("each row must be a dict")
            if row_id_col not in entry:
                raise TableSerializationError(
                    f"row is missing required '{row_id_col}' key"
                )
            cells = entry.get("cells", {}) or {}
            record: dict[str, Any] = {row_id_col: str(entry[row_id_col])}
            for col in columns:
                record[col.id] = cells.get(col.id)
            records.append(record)

        column_names = [row_id_col] + [col.id for col in columns]
        df = pd.DataFrame(records, columns=column_names)

        return cls(
            df,
            columns,
            linked_groups={},
            row_id_col=row_id_col,
            level_col=None,
            parent_id_col=None,
            label_col=None,
            is_total_col=None,
            partial=True,
        )

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

            is_total = False
            if self._is_total_col is not None:
                is_total = bool(record.get(self._is_total_col, False))

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
                    "is_total": is_total,
                    "parent_id": parent_id,
                    "cells": cells,
                }
            )
        return rows
