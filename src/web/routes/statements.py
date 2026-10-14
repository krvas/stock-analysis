from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.adjustments.specs import describe
from src.models.table import statement_table_from_dataframe
from src.web.adjusted_statements import load_for_basis
from src.web.page_types import StatementPage
from src.web.routes.settings import NavContext, render_with_settings, settings_for
from src.web.settings import Settings
from src.web.statements_registry import STATEMENT_PAGES, get_statement_page

router = APIRouter(tags=["statements"])


def _normalize_ticker(ticker: str) -> str:
    return ticker.upper().strip()


def statement_context(
    symbol: str, page: StatementPage, settings: Settings
) -> dict[str, Any]:
    loaded = load_for_basis(symbol, settings.period, settings.basis)
    statement = loaded.statements.get(page.slug)
    frame = statement.project(settings.view, settings.recent_periods(statement.periods))
    return {
        "ticker": symbol,
        "page": page,
        "period": settings.period,
        "basis": settings.basis,
        "adjustments": describe(loaded.specs),
        "statement_table": statement_table_from_dataframe(frame).serialize(),
        "active_nav": "statements",
    }


@router.get("/statements/{ticker}")
def statements_redirect(ticker: str) -> RedirectResponse:
    symbol = _normalize_ticker(ticker)
    return RedirectResponse(
        url=f"/statements/{symbol}/{STATEMENT_PAGES[0].slug}", status_code=307
    )


@router.get("/statements/{ticker}/{statement}", response_class=HTMLResponse)
def statement_page(request: Request, ticker: str, statement: str) -> HTMLResponse:
    page = get_statement_page(statement)
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown statement")
    symbol = _normalize_ticker(ticker)
    settings = settings_for(request, page.settings)
    return render_with_settings(
        request,
        "statements/statement_view.html",
        statement_context(symbol, page, settings),
        settings=settings,
        nav=NavContext(
            prefix=f"/statements/{symbol}", pages=STATEMENT_PAGES, page=page
        ),
    )
