"""Calc-linkbase residuals of a reported :class:`Statement`.

``residual = reported(parent) − Σ weight·child`` per calc parent × period, on
raw signs; the adjustments engine uses these to reproduce reported totals.

Pure: pandas only, no I/O.
See ``specs/adjustments_architecture.md`` §6.1.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.models.statement import Statement, bool_flag

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
    "n_nan_weight_children",
)


def _first_per_concept(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the first row (frame order) of each concept.

    A concept presented twice in one filing gets ``#n`` row ids (see
    :func:`get_row_id`); the cache builder always adds ``#1`` before ``#2``,
    so frame order picks ``#1``.
    """
    return df[~df["concept"].duplicated(keep="first")]


def calc_residuals(statement: Statement) -> pd.DataFrame:
    """Calc-linkbase residuals of ``statement``, one row per parent × period.

    ``residual = reported(parent) − Σ weight·child`` over the parent's
    non-dimensional calc children (:meth:`Statement.children`), on **raw**
    signs (the frame's own values; ``preferred_sign`` is display-only).
    See ``specs/adjustments_architecture.md`` §6.1: the engine recomputes
    dirty totals as ``Σ weight·child + residual`` so zero specs reproduce
    reported values exactly.

    - Parents: non-dimensional rows with ≥1 non-dimensional child. When a
      concept has several non-dimensional rows (``#n`` duplicates), only the
      first (``#1``) is a parent, and only the first of a duplicated child
      concept is summed — ``parent_concept`` names a concept, not a row.
    - Periods where the parent value is NaN are skipped. NaN children count
      as 0 and are counted in ``n_nan_children``. A child whose ``weight`` is
      NaN (unknown in every cached filing) is left out of the sum rather than
      guessed, and counted in ``n_nan_weight_children``; a frame without a
      ``weight`` column weighs every child 1.
    - ``relative = residual / |reported|`` (``±inf`` when reported is 0 and
      the residual is not, NaN when both are 0).
    - Known, accepted residual: diluted weighted-average shares
      (``WeightedAverageNumberOfDilutedSharesOutstanding``) always leaves a
      residual equal to the dilutive effect, because edgartools takes its calc
      tree from the EPS-note role (diluted = basic + incremental shares) and
      the incremental-shares child is not on the income statement.

    Columns: :data:`RESIDUAL_COLUMNS`. Pure: no I/O, frame untouched.
    """
    df = statement.frame
    periods = statement.periods
    records: list[dict[str, Any]] = []
    if "parent_concept" not in df.columns or not periods:
        return pd.DataFrame(columns=list(RESIDUAL_COLUMNS))

    values = df[periods].apply(pd.to_numeric, errors="coerce").astype(float)
    non_dimensional = df[~bool_flag(df, "dimension")]
    child_concepts = set(non_dimensional["parent_concept"].dropna())
    parents = _first_per_concept(
        non_dimensional[non_dimensional["concept"].isin(child_concepts)]
    )

    for index, parent in parents.iterrows():
        children = _first_per_concept(statement.children(parent["row_id"]))
        if children.empty:
            continue
        weights = pd.to_numeric(
            children.get("weight", pd.Series(1.0, index=children.index)),
            errors="coerce",
        )
        n_nan_weight = int(weights.isna().sum())
        child_values = values.loc[children.index]
        for period in periods:
            reported = values.at[index, period]
            if np.isnan(reported):
                continue
            column = child_values[period]
            # NaN weight → NaN product, which ``sum`` skips.
            computed = float((column.fillna(0.0) * weights).sum())
            residual = float(reported - computed)
            if reported != 0:
                relative = residual / abs(reported)
            elif residual != 0:
                relative = float(np.copysign(np.inf, residual))
            else:
                relative = float("nan")
            records.append(
                {
                    "row_id": parent["row_id"],
                    "concept": parent["concept"],
                    "label": parent.get("label"),
                    "period": period,
                    "reported": float(reported),
                    "computed": computed,
                    "residual": residual,
                    "relative": relative,
                    "n_children": len(children),
                    "n_nan_children": int(column.isna().sum()),
                    "n_nan_weight_children": n_nan_weight,
                }
            )
    return pd.DataFrame.from_records(records, columns=list(RESIDUAL_COLUMNS))
