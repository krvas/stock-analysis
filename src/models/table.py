"""Column-based table serialization for financial statement views."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import pandas as pd

from src.models.statement import STATEMENT_METADATA_COLUMNS

ColumnKind = Literal["static", "input", "link"]
ColumnDtype = Literal["number", "string", "boolean"]
LinkedGroupType = Literal["pct_of_base"]
NumberFormat = Literal["financial", "percent", "integer"]

_NUMBER_FORMATS: frozenset[str] = frozenset({"financial", "percent", "integer"})

# Non-period columns of a statement view frame. Includes every column a
# :class:`~src.models.statement.Statement` frame / projection carries (e.g.
# ``row_id``, ``dimension``, ``tags``) so none is mistaken for a period.
STATEMENT_VIEW_METADATA_COLUMNS: frozenset[str] = (
    frozenset(
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
    | STATEMENT_METADATA_COLUMNS
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


@dataclass(frozen=True)
class CalculatedCellSpec:
    """A cell the frontend computes from other cells of the same table.

    ``expr`` is a JSON expression tree evaluated client-side
    (``components/calculated_cell.js``). Node shapes:
    ``{"cell": [row_id, col_id]}``, ``{"const": number}``,
    ``{"op": "add" | "mul", "args": [expr, ...]}``.
    """

    row_id: str
    col_id: str
    expr: dict[str, Any]


class TableSerializationError(ValueError):
    """Invalid table configuration or source data for serialization."""


_EXPR_OPS: frozenset[str] = frozenset({"add", "mul"})


def _validate_expr(
    expr: object, row_ids: set[str], column_ids: set[str], where: str
) -> None:
    """Check an expression tree's node shapes and that cell refs exist."""
    if not isinstance(expr, dict) or len(expr) == 0:
        raise TableSerializationError(f"{where}: expression node must be a dict")
    if "cell" in expr:
        ref = expr["cell"]
        if len(expr) != 1 or not isinstance(ref, list) or len(ref) != 2:
            raise TableSerializationError(
                f"{where}: cell node must be {{'cell': [row_id, col_id]}}"
            )
        row_id, col_id = ref
        if row_id not in row_ids:
            raise TableSerializationError(f"{where}: unknown row '{row_id}'")
        if col_id not in column_ids:
            raise TableSerializationError(f"{where}: unknown column '{col_id}'")
        return
    if "const" in expr:
        value = expr["const"]
        if (
            len(expr) != 1
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise TableSerializationError(f"{where}: const node must be a number")
        return
    if "op" in expr:
        args = expr.get("args")
        if set(expr) != {"op", "args"} or expr["op"] not in _EXPR_OPS:
            raise TableSerializationError(
                f"{where}: op node must be {{'op': 'add'|'mul', 'args': [...]}}"
            )
        if not isinstance(args, list) or len(args) == 0:
            raise TableSerializationError(f"{where}: op args must be a non-empty list")
        for arg in args:
            _validate_expr(arg, row_ids, column_ids, where)
        return
    raise TableSerializationError(f"{where}: unknown expression node {expr!r}")


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
    """Build a :class:`Table` for a standard multi-period statement view.

    Rows are keyed by the frame's ``row_id`` column, which every
    :meth:`~src.models.statement.Statement.project` frame carries (formed by
    :func:`~src.models.statement.get_row_id`). A frame without ``row_id``
    raises :class:`TableSerializationError` rather than having ids re-derived
    here: a re-derivation could not know a row's within-filing occurrence, so
    it could silently disagree with the ids the statement cache assigned.
    """
    return Table(
        df,
        period_column_specs(df),
        linked_groups={},
        row_id_col="row_id",
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
        origin_col: str | None = "origin",
        calculated_cells: list[CalculatedCellSpec] | None = None,
        no_input_cells: list[tuple[str, str]] | None = None,
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
        if (
            resolved_is_total_col is not None
            and resolved_is_total_col not in df.columns
        ):
            resolved_is_total_col = None

        resolved_origin_col = origin_col
        if resolved_origin_col is not None and resolved_origin_col not in df.columns:
            resolved_origin_col = None

        row_ids = set(df[row_id_col].astype(str))
        calc_specs = list(calculated_cells or [])
        if calc_specs:
            for spec in calc_specs:
                where = f"calculated cell ({spec.row_id!r}, {spec.col_id!r})"
                if spec.row_id not in row_ids:
                    raise TableSerializationError(f"{where}: unknown row")
                if spec.col_id not in column_id_set:
                    raise TableSerializationError(f"{where}: unknown column")
                _validate_expr(spec.expr, row_ids, column_id_set, where)

        input_column_ids = {spec.id for spec in columns if spec.kind == "input"}
        omitted_inputs = [(str(r), str(c)) for r, c in no_input_cells or []]
        for row_id, col_id in omitted_inputs:
            if row_id not in row_ids:
                raise TableSerializationError(f"no_input_cells: unknown row '{row_id}'")
            if col_id not in input_column_ids:
                raise TableSerializationError(
                    f"no_input_cells: '{col_id}' is not an input column"
                )

        self._df = df
        self._columns = columns
        self._linked_groups = linked_groups
        self._row_id_col = row_id_col
        self._level_col = resolved_level_col
        self._parent_id_col = parent_id_col
        self._label_col = label_col
        self._is_total_col = resolved_is_total_col
        self._origin_col = resolved_origin_col
        self._calculated_cells = calc_specs
        self._no_input_cells = omitted_inputs
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
            "calculated_cells": [asdict(spec) for spec in self._calculated_cells],
            "no_input_cells": [[r, c] for r, c in self._no_input_cells],
        }

    def to_dict(self) -> dict[str, Any]:
        """Alias for :meth:`serialize` (template / API embedding)."""
        return self.serialize()

    def find_row_id(self, key: str) -> str | None:
        """Return ``key`` if it exactly matches a value of ``row_id_col``, else None.

        Surrounding whitespace in ``key`` is ignored; a blank key returns None.
        No other column is consulted, so callers must pass keys in the same
        form as this table's row ids.
        """
        row_key = str(key).strip()
        if not row_key:
            return None
        if row_key in self._df[self._row_id_col].astype(str).values:
            return row_key
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

            row: dict[str, Any] = {
                "id": row_id_str,
                "label": str(record.get(self._label_col, "") or ""),
                "level": level,
                "is_total": is_total,
                "parent_id": parent_id,
                "cells": cells,
            }
            if self._origin_col is not None:
                row["origin"] = _cell_value_from_raw(record.get(self._origin_col))
            rows.append(row)
        return rows
