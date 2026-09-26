"""Context builders for Adjustment wizard sub-pages."""

from __future__ import annotations

import logging

import pandas as pd

from src.api.edgartools.source import PeriodType, get_statement_views
from src.api.edgartools.standard_terms import OPERATING_EXPENSES
from src.database.wizard_manager import WizardDatabaseManager
from src.models.table import ColumnSpec, Table, period_column_specs

logger = logging.getLogger(__name__)

OPEX_TO_CAPEX_ADJUSTMENT_TYPE = "opex_to_capex"

# Wizard HTTP/route layer only supports a single exchange for now; the
# underlying DB layer (WizardDatabaseManager, adjustment_preferences) still
# has a real exchange column/parameter, but nothing above it threads a value
# through, so it's hardcoded here.
DEFAULT_EXCHANGE = "NASDAQ"

OPEX_TO_CAPEX_INPUT_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(id="capitalize", label="Capitalize", kind="input", dtype="boolean"),
    ColumnSpec(id="years", label="Years", kind="input", dtype="number"),
]


def _apply_saved_opex_to_capex_preferences(
    table: Table,
    ticker: str,
) -> None:
    with WizardDatabaseManager(read_only=True) as db:
        prefs = db.read_adjustment_preferences(ticker, DEFAULT_EXCHANGE)
    if prefs.empty:
        return

    saved = prefs[prefs["adjustment_type"] == OPEX_TO_CAPEX_ADJUSTMENT_TYPE]
    if saved.empty:
        return

    for _, pref in saved.iterrows():
        base_concept = pref["base_concept"]
        if base_concept is None or (isinstance(base_concept, float) and pd.isna(base_concept)):
            continue
        row_id = table.find_row_id(str(base_concept))
        if row_id is None:
            logger.warning(
                "Skipping opex-to-capex preference for unknown base_concept %r",
                base_concept,
            )
            continue
        table.set_cell("capitalize", row_id, True)
        table.set_cell("years", row_id, float(pref["value"]))


def opex_to_capex_context(
    ticker: str,
    period: PeriodType,
) -> dict[str, object]:
    views = get_statement_views(ticker=ticker, statement_type="income", period=period, num_periods=2)
    df = views["detailed"]
    opex = df[df["standard_concept"].isin(OPERATING_EXPENSES)]
    columns = period_column_specs(opex) + OPEX_TO_CAPEX_INPUT_COLUMNS
    table = Table(
        opex,
        columns,
        linked_groups={},
        row_id_col="standard_concept",
        level_col="level",
        parent_id_col=None,
    )
    _apply_saved_opex_to_capex_preferences(table, ticker)
    return {"opex_table": table.serialize()}
