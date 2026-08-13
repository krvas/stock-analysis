"""Cross-company screener HTML views (placeholder until analytics helpers exist)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.templating import templates

router = APIRouter(tags=["screener"])


@router.get("/screener", response_class=HTMLResponse)
def screener_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "screener/index.html",
        {"active_nav": "screener"},
    )
