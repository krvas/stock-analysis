"""AJAX endpoints for Adjustment subpage content."""

from src.api.edgartools.standard_terms import OPERATING_EXPENSES
from src.api.edgartools.source import PeriodType, get_statement_views
from src.models.table import ColumnSpec, Table, period_column_specs


def opex_to_capex_context(ticker: str, period: PeriodType) -> dict[str, object]:
    views = get_statement_views(ticker=ticker, statement_type="income", period=period, num_periods=2)
    df = views["detailed"]
    opex = df[df["standard_concept"].isin(OPERATING_EXPENSES)]
    columns = period_column_specs(opex) + [
        ColumnSpec(id="capitalize", label="Capitalize", kind="input", dtype="boolean"),
        ColumnSpec(id="years", label="Years", kind="input", dtype="number"),
    ]
    table = Table(
        opex,
        columns,
        linked_groups={},
        row_id_col="concept",
        level_col="level",
        parent_id_col=None,
    )
    return {"opex_table": table.serialize()}
