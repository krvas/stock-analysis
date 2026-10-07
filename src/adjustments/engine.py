"""Apply adjustment specs to a reported :class:`StatementSet`.

``apply_adjustments(base, specs, until=None)`` returns a new, adjusted set;
``base`` is never mutated. Each type returns inserted rows and value
overrides; the engine wires inserted rows into each period's calc tree and
recomputes every dirty ancestor as ``Σ weight·child + residual`` (residual
from the *reported* statement), so zero specs reproduce reported values
exactly. Net income is synced income → cashflow.

Pure: no I/O. See ``specs/adjustments_architecture.md`` §2, §6.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from src.adjustments.base import AdjustmentResult, AdjustmentSpec, NewRow
from src.adjustments.registry import ADJUSTMENT_ORDER, get_adjustment_type
from src.models.calc_residuals import calc_residuals
from src.models.statement import (
    STATEMENT_TYPES,
    Statement,
    StatementSet,
    StatementType,
    bool_flag,
)

logger = logging.getLogger(__name__)

# Concepts that carry the same value on the income and cashflow statements.
SYNCED_CONCEPTS: tuple[str, ...] = ("us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss")


def ordered_specs(
    specs: Iterable[AdjustmentSpec], until: str | None = None
) -> list[AdjustmentSpec]:
    """Specs in pipeline order, stopping before type ``until`` (if given)."""
    rank = {type_id: i for i, type_id in enumerate(ADJUSTMENT_ORDER)}
    limit = rank[until] if until is not None else len(ADJUSTMENT_ORDER)
    kept = [s for s in specs if s.type_id in rank and rank[s.type_id] < limit]
    return sorted(kept, key=lambda s: rank[s.type_id])


def apply_adjustments(
    base: StatementSet,
    specs: Sequence[AdjustmentSpec],
    until: str | None = None,
) -> StatementSet:
    residuals = {st: _residual_lookup(base.get(st)) for st in STATEMENT_TYPES}
    current = base
    for spec in ordered_specs(specs, until):
        adjustment = get_adjustment_type(spec.type_id)
        try:
            result = adjustment.apply(current, spec)
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping %s adjustment: %s", spec.type_id, exc)
            continue
        current = _apply_result(
            current, result, residuals, f"adjustment:{spec.type_id}"
        )
    return current


def _residual_lookup(statement: Statement) -> dict[tuple[str, str], float]:
    frame = calc_residuals(statement)
    return {
        (row.period, row.concept): float(row.residual)
        for row in frame.itertuples(index=False)
    }


def _apply_result(
    ss: StatementSet,
    result: AdjustmentResult,
    residuals: dict[StatementType, dict[tuple[str, str], float]],
    origin: str,
) -> StatementSet:
    statements = {st: ss.get(st) for st in STATEMENT_TYPES}
    dirty: dict[StatementType, set[str]] = {st: set() for st in STATEMENT_TYPES}

    for override in result.overrides:
        st = statements[override.statement]
        values = {p: v for p, v in override.values.items() if p in st.periods}
        adjusted = st.with_values(override.row_id, values).frame.copy()
        adjusted.loc[adjusted["row_id"] == override.row_id, "origin"] = origin
        statements[override.statement] = Statement(
            adjusted, st.statement_type, st.calc_edges
        )
        concept = st.frame.loc[st.frame["row_id"] == override.row_id, "concept"]
        dirty[override.statement].update(concept.head(1))

    for new_row in result.new_rows:
        st = statements[new_row.statement]
        statements[new_row.statement] = _insert_row(st, new_row, origin)
        dirty[new_row.statement].add(new_row.concept)

    for st_type in ("balance", "income", "cashflow"):
        if st_type == "cashflow":
            statements["cashflow"] = _sync_from_income(
                statements["income"], statements["cashflow"], dirty
            )
        if dirty[st_type]:
            statements[st_type], touched = _recompute(
                statements[st_type], dirty[st_type], residuals[st_type]
            )
            dirty[st_type] |= touched
    return StatementSet(**statements)


def _insert_row(statement: Statement, new_row: NewRow, origin: str) -> Statement:
    periods = statement.periods
    row = {
        "concept": new_row.concept,
        "row_id": new_row.concept,
        "label": new_row.label,
        "origin": origin,
        "tags": new_row.tags,
        "level": _level_after(statement, new_row.after),
        "is_total": new_row.is_total,
        "abstract": False,
        "dimension": False,
        "in_standard": True,
    }
    for period in periods:
        value = new_row.values.get(period)
        row[period] = np.nan if value is None else float(value)
    after = new_row.after if new_row.after in set(statement.frame["row_id"]) else None
    inserted = statement.insert(row, after=after)

    edges = [statement.calc_edges]
    parents = new_row.parent_concept
    if parents is not None:
        tree = statement.calc_edges
        for period in periods:
            parent = parents.get(period) if isinstance(parents, dict) else parents
            if parent is None:
                continue
            in_tree = (tree["period"] == period) & (
                (tree["parent_concept"] == parent) | (tree["concept"] == parent)
            )
            if not in_tree.any():
                continue
            edges.append(
                pd.DataFrame(
                    {
                        "period": [period],
                        "concept": [new_row.concept],
                        "parent_concept": [parent],
                        "weight": [float(new_row.weight)],
                    }
                )
            )
    return Statement(
        inserted.frame, statement.statement_type, pd.concat(edges, ignore_index=True)
    )


def _level_after(statement: Statement, after: str | None) -> int:
    frame = statement.frame
    if after is None or "level" not in frame.columns:
        return 1
    match = frame.index[frame["row_id"] == after]
    if len(match) == 0:
        return 1
    level = pd.to_numeric(frame.at[match[0], "level"], errors="coerce")
    return 1 if pd.isna(level) else int(level)


def _first_rows(frame: pd.DataFrame) -> pd.Series:
    """concept → index of its first non-dimensional row."""
    rows = frame[~bool_flag(frame, "dimension")]
    rows = rows[~rows["concept"].duplicated(keep="first")]
    return pd.Series(rows.index, index=rows["concept"])


def _sync_from_income(
    income: Statement,
    cashflow: Statement,
    dirty: dict[StatementType, set[str]],
) -> Statement:
    income_rows = _first_rows(income.frame)
    cash_rows = _first_rows(cashflow.frame)
    for concept in SYNCED_CONCEPTS:
        if concept not in dirty["income"]:
            continue
        if concept not in income_rows.index or concept not in cash_rows.index:
            continue
        source = income.frame.loc[income_rows[concept]]
        values = {
            p: float(source[p])
            for p in cashflow.periods
            if p in income.periods and pd.notna(source[p])
        }
        row_id = cashflow.frame.at[cash_rows[concept], "row_id"]
        cashflow = cashflow.with_values(row_id, values)
        dirty["cashflow"].add(concept)
    return cashflow


def _recompute(
    statement: Statement,
    dirty: set[str],
    residuals: dict[tuple[str, str], float],
) -> tuple[Statement, set[str]]:
    """Recompute every calc ancestor of ``dirty`` concepts, per period.

    Returns the new statement and the recomputed concepts.
    """
    frame = statement.frame.copy()
    rows = _first_rows(frame)
    edges = statement.calc_edges
    touched: set[str] = set()
    for period in statement.periods:
        tree = edges[edges["period"] == period]
        parent_of = dict(zip(tree["concept"], tree["parent_concept"], strict=True))
        children = tree.groupby("parent_concept")
        values = pd.to_numeric(frame[period], errors="coerce").astype(float)
        frame[period] = values
        pending = {parent_of[c] for c in dirty if c in parent_of}
        seen: set[str] = set()
        while pending:
            # Recompute deepest parents first so each sees final child values.
            parent = max(pending, key=lambda c: _depth(c, parent_of))
            pending.discard(parent)
            if parent in seen or parent not in rows.index:
                continue
            seen.add(parent)
            touched.add(parent)
            index = rows[parent]
            if pd.isna(frame.at[index, period]):
                continue
            group = children.get_group(parent)
            total = residuals.get((period, parent), 0.0)
            for child, weight in zip(group["concept"], group["weight"], strict=True):
                if child in rows.index:
                    child_value = frame.at[rows[child], period]
                    if pd.notna(child_value):
                        total += weight * child_value
            frame.at[index, period] = total
            if parent in parent_of:
                pending.add(parent_of[parent])
    return Statement(frame, statement.statement_type, statement.calc_edges), touched


def _depth(concept: str, parent_of: dict[str, str]) -> int:
    depth = 0
    while concept in parent_of and depth < 100:
        concept = parent_of[concept]
        depth += 1
    return depth
