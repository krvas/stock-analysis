"""AJAX endpoints for Adjustment subpage content."""

from src.api.edgartools.standard_terms import OPERATING_EXPENSES
from src.api.edgartools.source import PeriodType, get_statement_views
from src.models.edgartools.html_renderer import serialize_line_item_view


def opex_to_capex_context(ticker: str, period: PeriodType) -> dict[str, object]:
    views = get_statement_views(ticker=ticker, statement_type="income", period=period, num_periods=2)
    df = views["detailed"]
    opex = df[df["standard_concept"].isin(OPERATING_EXPENSES)]
    return {
        "opex_table": serialize_line_item_view(opex)
    }
