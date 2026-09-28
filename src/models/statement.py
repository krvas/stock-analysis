"""Reported financial statements as immutable, edgartools-shaped DataFrames.

A :class:`Statement` wraps one statement's frame whose columns are exactly
edgartools' ``to_dataframe`` metadata columns (same names) plus a few columns we
add (``row_id``, ``tags``, ``origin``, ``is_total``); every other column is a
period column (ISO date string, newest first). Values are stored with **raw**
XBRL signs; ``preferred_sign`` is applied only in :meth:`Statement.project`.

Pure domain module: pandas only, no edgartools import, no I/O.
See ``specs/adjustments_architecture.md`` §3–§5.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

StatementType = Literal["income", "balance", "cashflow"]
StatementView = Literal["summary", "standard", "detailed"]

STATEMENT_TYPES: tuple[StatementType, ...] = ("income", "balance", "cashflow")
STATEMENT_VIEWS: tuple[StatementView, ...] = ("summary", "standard", "detailed")

# Metadata columns emitted by edgartools 5.47 ``Statement.to_dataframe``.
# (edgartools can also emit ``unit`` / ``point_in_time``; we don't retain them.)
EDGARTOOLS_METADATA_COLUMNS: tuple[str, ...] = (
    "concept",
    "label",
    "standard_concept",
    "level",
    "abstract",
    "dimension",
    "is_breakdown",
    "dimension_axis",
    "dimension_member",
    "dimension_member_label",
    "dimension_label",
    "balance",
    "weight",
    "preferred_sign",
    "parent_concept",
    "parent_abstract_concept",
)

# Columns we add on top of edgartools' metadata.
ADDED_COLUMNS: tuple[str, ...] = ("row_id", "tags", "origin", "is_total")

STATEMENT_METADATA_COLUMNS: frozenset[str] = frozenset(
    EDGARTOOLS_METADATA_COLUMNS + ADDED_COLUMNS
)

# Columns returned by :meth:`Statement.project` ahead of the period columns.
# Restricted to what ``statement_table_from_dataframe`` treats as metadata
# (``src/models/table.py``) plus ``row_id``.
PROJECTION_METADATA_COLUMNS: tuple[str, ...] = (
    "row_id",
    "label",
    "concept",
    "standard_concept",
    "level",
    "is_total",
)

REPORTED_ORIGIN = "reported"

_TOTAL_LABEL_RE = re.compile(r"\btotal\b", re.IGNORECASE)


class DuplicateRowIdError(ValueError):
    """A statement frame produced the same ``row_id`` for more than one row."""


def is_total_label(label: object) -> bool:
    """Return whether ``label`` looks like a total row (contains the word 'total')."""
    if _is_missing(label):
        return False
    return bool(_TOTAL_LABEL_RE.search(str(label)))


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # list-like values: not a scalar missing marker
        return False


def _clean_str(value: object) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def get_row_id(row: Mapping[str, Any] | pd.Series, *, occurrence: int = 1) -> str:
    """Return the stable row id for one statement row.

    This is the **only** place row ids are formed. Format:

    - non-dimensional row: ``concept`` (e.g. ``us-gaap_Revenues``)
    - dimensional row: ``concept|axis=member``
      (e.g. ``us-gaap_Revenues|srt_ProductOrServiceAxis=us-gaap_ProductMember``)
    - ``occurrence`` > 1 appends ``#<occurrence>``
      (e.g. ``us-gaap_CashCashEquivalents...#2``)

    A row counts as dimensional when it has a ``dimension_axis`` or
    ``dimension_member``; NaN/None/blank values are treated as absent.

    The base id is not unique on its own: edgartools only exposes the
    *primary* (first) axis/member of a multi-axis row, and a filer can present
    the same concept twice non-dimensionally within one filing (e.g. cash
    beginning/end of period on the cash flow statement). The cache builder
    passes the 1-based ``occurrence`` of the base id within a filing to keep
    those rows apart. :class:`Statement` still detects any remaining
    duplicates and raises :class:`DuplicateRowIdError` rather than deduping.
    """
    if occurrence < 1:
        raise ValueError("occurrence must be >= 1")
    concept = _clean_str(row.get("concept"))
    if concept is None:
        raise ValueError("cannot form a row id for a row without a concept")
    axis = _clean_str(row.get("dimension_axis"))
    member = _clean_str(row.get("dimension_member"))
    base = (
        concept
        if axis is None and member is None
        else f"{concept}|{axis or ''}={member or ''}"
    )
    return base if occurrence == 1 else f"{base}#{occurrence}"


def _normalize_tags(value: object) -> tuple[str, ...]:
    """Coerce a ``tags`` cell to a sorted tuple of strings.

    Tags are stored as tuples rather than sets because pyarrow writes a
    list-like cell as ``list<string>`` (and reads it back as a numpy array),
    while sets are not parquet-serializable. Sorting keeps them deterministic.
    """
    if isinstance(value, str):
        return (value,)
    if value is None or (np.ndim(value) == 0 and _is_missing(value)):
        return ()
    return tuple(sorted({str(tag) for tag in value}))


def _bool_flag(frame: pd.DataFrame, column: str) -> pd.Series:
    """Boolean mask for an edgartools flag column; missing column/None → False."""
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[column].eq(True)


def _check_unique_row_ids(row_ids: pd.Series) -> None:
    duplicated = row_ids[row_ids.duplicated(keep=False)]
    if not duplicated.empty:
        names = sorted(set(duplicated.astype(str)))
        raise DuplicateRowIdError(
            f"duplicate row_id(s) in statement: {', '.join(names[:10])}"
            + (f" (+{len(names) - 10} more)" if len(names) > 10 else "")
        )


class Statement:
    """One financial statement (income, balance or cashflow).

    Treat instances as immutable: :attr:`frame` must not be mutated, and every
    transforming method returns a new :class:`Statement`.
    """

    def __init__(self, frame: pd.DataFrame, statement_type: StatementType) -> None:
        if statement_type not in STATEMENT_TYPES:
            raise ValueError(f"unknown statement_type '{statement_type}'")

        df = frame.reset_index(drop=True).copy()
        if "concept" not in df.columns:
            raise ValueError("statement frame must have a 'concept' column")

        if "row_id" not in df.columns:
            df["row_id"] = [get_row_id(row) for _, row in df.iterrows()]
        if "tags" not in df.columns:
            df["tags"] = pd.Series([()] * len(df), index=df.index, dtype=object)
        else:
            df["tags"] = pd.Series(
                [_normalize_tags(v) for v in df["tags"]], index=df.index, dtype=object
            )
        if "origin" not in df.columns:
            df["origin"] = REPORTED_ORIGIN
        else:
            df["origin"] = df["origin"].where(df["origin"].notna(), REPORTED_ORIGIN)
        if "is_total" not in df.columns:
            labels = df["label"] if "label" in df.columns else [None] * len(df)
            df["is_total"] = [is_total_label(label) for label in labels]

        _check_unique_row_ids(df["row_id"])

        self._frame = df
        self.statement_type: StatementType = statement_type

    def __repr__(self) -> str:
        return (
            f"Statement({self.statement_type!r}, rows={len(self._frame)}, "
            f"periods={self.periods})"
        )

    @property
    def frame(self) -> pd.DataFrame:
        """Underlying frame (raw signs). Do not mutate."""
        return self._frame

    @property
    def periods(self) -> list[str]:
        """Period columns in frame order (newest first)."""
        return [c for c in self._frame.columns if c not in STATEMENT_METADATA_COLUMNS]

    def _row_index(self, row_id: str) -> int:
        matches = np.flatnonzero(self._frame["row_id"].to_numpy() == row_id)
        if len(matches) == 0:
            raise KeyError(f"row_id '{row_id}' not found in {self.statement_type}")
        return int(matches[0])

    def find(
        self,
        concept: str | None = None,
        standard_concept: str | None = None,
        include_dimensional: bool = False,
    ) -> pd.DataFrame:
        """Rows matching ``concept`` and/or ``standard_concept`` (both if given)."""
        df = self._frame
        mask = pd.Series(True, index=df.index)
        if concept is not None:
            mask &= df["concept"].eq(concept)
        if standard_concept is not None:
            if "standard_concept" not in df.columns:
                return df.iloc[0:0].copy()
            mask &= df["standard_concept"].eq(standard_concept)
        if not include_dimensional:
            mask &= ~_bool_flag(df, "dimension")
        return df[mask].copy()

    def children(self, row_id: str) -> pd.DataFrame:
        """Non-dimensional calc children of ``row_id`` (via ``parent_concept``)."""
        df = self._frame
        concept = df["concept"].iloc[self._row_index(row_id)]
        if "parent_concept" not in df.columns:
            return df.iloc[0:0].copy()
        mask = df["parent_concept"].eq(concept) & ~_bool_flag(df, "dimension")
        return df[mask].copy()

    def insert(self, row: Mapping[str, Any], after: str | None = None) -> Statement:
        """Return a new statement with ``row`` inserted after ``after`` (else appended).

        ``row`` must supply ``concept`` and ``origin`` (e.g.
        ``"adjustment:opex_to_capex"``); ``row_id`` is derived via
        :func:`get_row_id` when absent and must not already exist.
        """
        if _clean_str(row.get("origin")) is None:
            raise ValueError("inserted rows must supply an 'origin'")
        allowed = set(self._frame.columns) | STATEMENT_METADATA_COLUMNS
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ValueError(f"unknown column(s) for inserted row: {unknown}")

        record = {col: row.get(col, np.nan) for col in self._frame.columns}
        for col in STATEMENT_METADATA_COLUMNS - set(self._frame.columns):
            if col in row:
                record[col] = row[col]
        record["row_id"] = _clean_str(row.get("row_id")) or get_row_id(row)
        record["tags"] = _normalize_tags(row.get("tags"))
        if "is_total" not in row:
            record["is_total"] = is_total_label(row.get("label"))
        if (self._frame["row_id"] == record["row_id"]).any():
            raise DuplicateRowIdError(
                f"row_id '{record['row_id']}' already exists in {self.statement_type}"
            )

        position = len(self._frame) if after is None else self._row_index(after) + 1
        records = self._frame.to_dict(orient="records")
        records.insert(position, record)
        columns = list(self._frame.columns) + [
            c for c in record if c not in self._frame.columns
        ]
        return Statement(
            pd.DataFrame.from_records(records, columns=columns), self.statement_type
        )

    def with_values(self, row_id: str, values: Mapping[str, float]) -> Statement:
        """Return a new statement with ``row_id``'s period values replaced."""
        position = self._row_index(row_id)
        unknown = sorted(set(values) - set(self.periods))
        if unknown:
            raise KeyError(f"unknown period(s): {unknown}")
        df = self._frame.copy()
        for period, value in values.items():
            if df[period].dtype != object and not pd.api.types.is_float_dtype(
                df[period]
            ):
                df[period] = df[period].astype(float)
            df.loc[position, period] = value
        return Statement(df, self.statement_type)

    def project(
        self,
        view: StatementView,
        periods: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Display frame for ``view`` over ``periods`` (None = all).

        Row filter uses edgartools' own flags: ``summary`` drops dimensional
        rows; ``standard`` also keeps dimensional rows that are not breakdowns;
        ``detailed`` keeps everything. Values are multiplied by
        ``preferred_sign`` where it is -1 (edgartools encodes it as ±1 floats,
        NaN/None when the presentation linkbase gives no preferred label —
        treated as +1). Non-abstract rows with no value in the requested
        periods are dropped. Abstract rows are always kept as-is; whether they
        should instead depend on surviving descendants is left to the
        projection-parity check against the legacy view frames.

        Output columns: :data:`PROJECTION_METADATA_COLUMNS` + period columns.
        """
        if view not in STATEMENT_VIEWS:
            raise ValueError(f"unknown view '{view}'")
        all_periods = self.periods
        selected = list(all_periods if periods is None else periods)
        unknown = sorted(set(selected) - set(all_periods))
        if unknown:
            raise KeyError(f"unknown period(s): {unknown}")

        df = self._frame
        dimension = _bool_flag(df, "dimension")
        if view == "summary":
            view_mask = ~dimension
        elif view == "standard":
            view_mask = ~dimension | ~_bool_flag(df, "is_breakdown")
        else:
            view_mask = pd.Series(True, index=df.index)

        values = df[selected].apply(pd.to_numeric, errors="coerce").astype(float)
        if "preferred_sign" in df.columns:
            sign = np.where(df["preferred_sign"].eq(-1), -1.0, 1.0)
            values = values.mul(sign, axis=0)

        has_value = values.notna().any(axis=1)
        keep = view_mask & (has_value | _bool_flag(df, "abstract"))

        meta = pd.DataFrame(index=df.index)
        for col in PROJECTION_METADATA_COLUMNS:
            meta[col] = df[col] if col in df.columns else None
        out = pd.concat([meta, values], axis=1)
        return out[keep].reset_index(drop=True)


@dataclass(frozen=True)
class StatementSet:
    """The three statements for one (company, period type)."""

    income: Statement
    balance: Statement
    cashflow: Statement
    periods: tuple[str, ...]

    def __post_init__(self) -> None:
        for statement_type in STATEMENT_TYPES:
            actual = getattr(self, statement_type).statement_type
            if actual != statement_type:
                raise ValueError(
                    f"StatementSet.{statement_type} has statement_type '{actual}'"
                )

    def get(self, statement_type: StatementType) -> Statement:
        if statement_type not in STATEMENT_TYPES:
            raise ValueError(f"unknown statement_type '{statement_type}'")
        return getattr(self, statement_type)

    def project(
        self,
        view: StatementView,
        periods: Sequence[str] | None = None,
    ) -> dict[StatementType, pd.DataFrame]:
        """:meth:`Statement.project` for all three statements."""
        return {
            statement_type: self.get(statement_type).project(view, periods)
            for statement_type in STATEMENT_TYPES
        }
