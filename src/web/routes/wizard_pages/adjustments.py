"""AJAX endpoints for Adjustment subpage content."""

import pandas as pd

from src.api.edgartools.standard_terms import OPERATING_EXPENSES

from src.api.edgartools.source import PeriodType, get_statement_views


def opex_to_capex_context(ticker: str, period: PeriodType) -> dict[str, object]:
    views = get_statement_views(ticker=ticker, statement_type="income", period=period, num_periods=2)
    df = views["detailed"]
    opex = df[df["standard_concept"].isin(OPERATING_EXPENSES)]
    return {
        "table": opex.to_html()
    }
