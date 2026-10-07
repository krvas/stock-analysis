"""Context builders for Adjustment wizard sub-pages."""

from __future__ import annotations

import logging

import pandas as pd

from src.api.edgartools.standard_terms import OPERATING_EXPENSES
from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import PeriodType
from src.models.table import ColumnSpec, Table, period_column_specs
from src.web.adjusted_statements import DEFAULT_EXCHANGE, load_adjusted

logger = logging.getLogger(__name__)

OPEX_TO_CAPEX_ADJUSTMENT_TYPE = "opex_to_capex"


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

    # ``base_concept`` holds a row id (see ``get_row_id``); the column keeps
    # its historical name. Keys are matched exactly -- no concept fallback.
    for _, pref in saved.iterrows():
        saved_row_id = pref["base_concept"]
        if saved_row_id is None or (
            isinstance(saved_row_id, float) and pd.isna(saved_row_id)
        ):
            continue
        row_id = table.find_row_id(str(saved_row_id))
        if row_id is None:
            logger.warning(
                "Skipping opex-to-capex preference for unknown row id %r",
                saved_row_id,
            )
            continue
        table.set_cell("capitalize", row_id, True)
        table.set_cell("years", row_id, float(pref["value"]))


def opex_to_capex_context(
    ticker: str,
    period: PeriodType,
) -> dict[str, object]:
    # Stage semantics: the opex page shows the input to opex-to-capex.
    _, staged, _ = load_adjusted(ticker, period, until=OPEX_TO_CAPEX_ADJUSTMENT_TYPE)
    income = staged.income
    df = income.project("detailed", income.periods[:2])
    # Selection by standard_concept; identity is the ``row_id`` from get_row_id.
    opex = df[df["standard_concept"].isin(OPERATING_EXPENSES)]
    columns = period_column_specs(opex) + OPEX_TO_CAPEX_INPUT_COLUMNS
    table = Table(
        opex,
        columns,
        linked_groups={},
        row_id_col="row_id",
        level_col="level",
        parent_id_col=None,
    )
    _apply_saved_opex_to_capex_preferences(table, ticker)
    return {"opex_table": table.serialize()}
