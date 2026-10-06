"""Single-company financial statement HTML views."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.api.edgartools.source import PeriodType, load_statement_set
from src.config import MAX_CACHE_QUARTERS, MAX_PERIODS_BY_PERIOD
from src.models.edgartools.html_renderer import build_statement_payload
from src.web.templating import templates

router = APIRouter(tags=["statements"])


def clamp_num_periods(num_periods: int, period: PeriodType, available: int) -> int:
    """Clamp a requested period count to the cache cap and what's available."""
    return min(num_periods, MAX_PERIODS_BY_PERIOD[period], available)


@router.get("/statements/{ticker}", response_class=HTMLResponse)
def statement_view(
    request: Request,
    ticker: str,
    period: PeriodType = Query(default="annual"),
    num_periods: int = Query(default=10, ge=1, le=MAX_CACHE_QUARTERS),
) -> HTMLResponse:
    """Serve an interactive statement page; toggles stay client-side."""
    symbol = ticker.upper().strip()
    statement_set = load_statement_set(symbol, period)
    statement_data = build_statement_payload(
        statement_set,
        ticker=symbol,
        period=period,
        num_periods=clamp_num_periods(num_periods, period, len(statement_set.periods)),
    )
    return templates.TemplateResponse(
        request,
        "statements/statement_view.html",
        {
            "statement_data": statement_data,
            "active_nav": "statements",
        },
    )
