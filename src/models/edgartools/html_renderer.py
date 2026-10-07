"""Serialize edgartools statement views for the HTML statement page."""

from __future__ import annotations

from typing import Any

from src.models.statement import (
    STATEMENT_TYPES,
    STATEMENT_VIEWS,
    Statement,
    StatementSet,
)
from src.models.table import statement_table_from_dataframe


def _serialize_views(statement: Statement, num_periods: int) -> dict[str, Any]:
    periods = statement.periods[:num_periods]
    return {
        view: statement_table_from_dataframe(
            statement.project(view, periods)
        ).serialize()
        for view in STATEMENT_VIEWS
    }


def build_statement_payload(
    statement_set: StatementSet,
    *,
    ticker: str,
    period: str,
    num_periods: int,
    adjusted: StatementSet | None = None,
    adjustments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the JSON payload embedded in the statement Jinja template.

    Each statement is projected to every view over its newest ``num_periods``
    periods; ``statements[type][view]`` is a ``Table.serialize()`` payload.
    ``adjusted_statements`` has the same shape for ``adjusted`` (else None).
    """

    def serialize(ss: StatementSet) -> dict[str, Any]:
        return {
            statement_type: _serialize_views(ss.get(statement_type), num_periods)
            for statement_type in STATEMENT_TYPES
        }

    return {
        "ticker": ticker,
        "period": period,
        "statements": serialize(statement_set),
        "adjusted_statements": serialize(adjusted) if adjusted is not None else None,
        "adjustments": adjustments or [],
    }
