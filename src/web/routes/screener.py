"""Cross-company screener HTML views (placeholder until analytics helpers exist)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.web.templating import templates

router = APIRouter(tags=["screener"])


@router.get("/screener", response_class=HTMLResponse)
def screener_index(
    request: Request, ticker: str | None = Query(default=None)
) -> HTMLResponse:
    """Placeholder page; ``ticker`` only keeps the nav on the current company."""
    return templates.TemplateResponse(
        request,
        "screener/index.html",
        {
            "active_nav": "screener",
            "ticker": ticker.upper().strip() if ticker else None,
        },
    )
