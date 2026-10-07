"""Calc-linkbase residuals of a reported :class:`Statement`.

``residual = reported(parent) − Σ weight·child`` per calc parent × period, on
raw signs, over each period's own calc tree (:attr:`Statement.calc_edges`);
the adjustments engine uses these to reproduce reported totals.

Pure: pandas only, no I/O.
See ``specs/adjustments_architecture.md`` §6.1.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from src.models.statement import Statement, StatementType, bool_flag

RESIDUAL_COLUMNS: tuple[str, ...] = (
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
)


def calc_residuals(statement: Statement) -> pd.DataFrame:
    """Calc-linkbase residuals of ``statement``, one row per parent × period.

    Per period ``p``, on ``p``'s own calc tree (the ``p`` rows of
    :attr:`Statement.calc_edges`: the statement-role tree of the filing
    ``p``'s values came from), ``residual = reported(parent) − Σ w·child``
    with the edge weights, on **raw** signs (the frame's own values;
    ``preferred_sign`` is display-only). See
    ``specs/adjustments_architecture.md`` §6.1: the engine recomputes dirty
    totals as ``Σ w·child + residual`` per period so zero specs reproduce
    reported values exactly.

    - Parents: ``parent_concept`` s of ``p``'s edges that have a
      non-dimensional row; children: ``p``'s edges under that parent, joined
      to rows by concept. Only the first non-dimensional row of a concept
      (``#1`` of ``#n`` duplicates) is a parent or a summed child — edges
      name concepts, not rows.
    - Periods where the parent value is NaN are skipped. A NaN child value
      counts as 0 and is counted in ``n_nan_children``. An edge whose child
      concept has no non-dimensional row (a calc child the statement does
      not present) contributes nothing and is counted in
      ``n_missing_children``; ``n_children`` counts the summed (presented)
      children only.
    - ``relative = residual / |reported|`` (``±inf`` when reported is 0 and
      the residual is not, NaN when both are 0).

    Rows are ordered by parent (frame order), then period (frame order).
    Columns: :data:`RESIDUAL_COLUMNS`. Pure: no I/O, frame untouched.
    """
    df = statement.frame
    periods = statement.periods
    edges = statement.calc_edges
    if edges.empty or not periods:
        return pd.DataFrame(columns=list(RESIDUAL_COLUMNS))

    values = df[periods].apply(pd.to_numeric, errors="coerce").astype(float)
    # Keep the first row (frame order) of each concept. A concept presented
    # twice in one filing gets ``#n`` row ids (see :func:`get_row_id`); the
    # cache builder always adds ``#1`` before ``#2``, so frame order picks ``#1``.
    non_dimensional = df[~bool_flag(df, "dimension")]
    first_rows = non_dimensional[~non_dimensional["concept"].duplicated(keep="first")]
    index_by_concept = pd.Series(first_rows.index, index=first_rows["concept"])
    period_order = {period: i for i, period in enumerate(periods)}

    keyed: list[tuple[int, int, dict[str, Any]]] = []
    for (period, parent_concept), group in edges.groupby(
        ["period", "parent_concept"], sort=False
    ):
        if parent_concept not in index_by_concept.index:
            continue
        parent_index = int(index_by_concept[parent_concept])
        reported = values.at[parent_index, period]
        if np.isnan(reported):
            continue
        child_index = group["concept"].map(index_by_concept)
        present = child_index.notna()
        child_values = values.loc[child_index[present].astype(int), period].to_numpy()
        weights = group.loc[present, "weight"].to_numpy()
        computed = float((np.nan_to_num(child_values, nan=0.0) * weights).sum())
        residual = float(reported - computed)
        if reported != 0:
            relative = residual / abs(reported)
        elif residual != 0:
            relative = float(np.copysign(np.inf, residual))
        else:
            relative = float("nan")
        parent = df.loc[parent_index]
        record = {
            "row_id": parent["row_id"],
            "concept": parent_concept,
            "label": parent.get("label"),
            "period": period,
            "reported": float(reported),
            "computed": computed,
            "residual": residual,
            "relative": relative,
            "n_children": int(present.sum()),
            "n_nan_children": int(np.isnan(child_values).sum()),
            "n_missing_children": int((~present).sum()),
        }
        keyed.append((parent_index, period_order[period], record))
    keyed.sort(key=lambda item: item[:2])
    return pd.DataFrame.from_records(
        [record for *_, record in keyed], columns=list(RESIDUAL_COLUMNS)
    )


def tagged_residuals(
    statements: Mapping[StatementType, Statement],
    *,
    ticker: str,
    period_type: str,
) -> pd.DataFrame:
    """:func:`calc_residuals` of every given statement, concatenated.

    Each statement's rows are prefixed with ``ticker`` / ``period_type`` /
    ``statement`` columns (in that order), statements in mapping order. With
    no statements the result is an empty frame with those columns plus
    :data:`RESIDUAL_COLUMNS`. Pure: no I/O.
    """
    frames = []
    for statement_type, statement in statements.items():
        frame = calc_residuals(statement)
        frame.insert(0, "statement", statement_type)
        frame.insert(0, "period_type", period_type)
        frame.insert(0, "ticker", ticker)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(
            columns=["ticker", "period_type", "statement", *RESIDUAL_COLUMNS]
        )
    return pd.concat(frames, ignore_index=True)
