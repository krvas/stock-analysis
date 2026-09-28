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
) -> dict[str, Any]:
    """Build the JSON payload embedded in the statement Jinja template.

    Each statement is projected to every view over its newest ``num_periods``
    periods; ``statements[type][view]`` is a ``Table.serialize()`` payload.
    """
    return {
        "ticker": ticker,
        "period": period,
        "statements": {
            statement_type: _serialize_views(
                statement_set.get(statement_type), num_periods
            )
            for statement_type in STATEMENT_TYPES
        },
    }
