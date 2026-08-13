"""Single-company financial statement HTML views."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.api.edgartools.source import get_statement_views
from src.models.edgartools.html_renderer import build_statement_payload
from src.web.templating import templates

router = APIRouter(tags=["statements"])

StatementType = Literal["income", "balance", "cashflow"]
PeriodType = Literal["annual", "quarterly"]


@router.get("/statements/{ticker}", response_class=HTMLResponse)
def statement_view(
    request: Request,
    ticker: str,
    statement_type: StatementType = Query(default="income"),
    period: PeriodType = Query(default="annual"),
    num_periods: int = Query(default=10, ge=1, le=40),
) -> HTMLResponse:
    """Serve an interactive statement page; view toggling stays client-side."""
    symbol = ticker.upper().strip()
    views = get_statement_views(symbol, statement_type, period, num_periods)
    statement_data = build_statement_payload(
        views,
        ticker=symbol,
        statement_type=statement_type,
        period=period,
    )
    return templates.TemplateResponse(
        request,
        "statements/statement_view.html",
        {
            "statement_data": statement_data,
            "active_nav": "statements",
        },
    )
