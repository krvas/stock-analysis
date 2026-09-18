"""Single-company financial statement HTML views."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.api.edgartools.source import get_all_statement_views
from src.models.edgartools.html_renderer import build_statement_payload
from src.web.templating import templates

router = APIRouter(tags=["statements"])

PeriodType = Literal["annual", "quarterly"]


@router.get("/statements/{ticker}", response_class=HTMLResponse)
def statement_view(
    request: Request,
    ticker: str,
    period: PeriodType = Query(default="annual"),
    num_periods: int = Query(default=10, ge=1, le=40),
) -> HTMLResponse:
    """Serve an interactive statement page; toggles stay client-side."""
    symbol = ticker.upper().strip()
    all_views = get_all_statement_views(symbol, period, num_periods)
    statement_data = build_statement_payload(
        all_views,
        ticker=symbol,
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
