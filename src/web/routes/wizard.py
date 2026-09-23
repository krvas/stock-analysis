"""HTML routes for the per-ticker analysis wizard skeleton."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import TemplateNotFound
from starlette.responses import Response

from src.web.templating import templates
from src.web.wizard_registry import (
    GROUP_LABELS,
    WIZARD_PAGES,
    Page,
    SubPage,
    first_subpage,
    get_page,
    get_subpage,
    grouped_pages,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wizard"])


def _normalize_ticker(ticker: str) -> str:
    return ticker.upper().strip()


def subpage_post_url(ticker: str, page_slug: str, subpage_slug: str) -> str:
    """Canonical POST URL for a wizard sub-page (``POST`` JSON body)."""
    return f"/wizard/{ticker}/{page_slug}/{subpage_slug}"


def _wizard_context(
    *,
    ticker: str,
    page: Page | None = None,
    subpage: SubPage | None = None,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "wizard_pages": WIZARD_PAGES,
        "wizard_groups": grouped_pages(),
        "page": page,
        "subpage": subpage,
        "group_label": GROUP_LABELS[page.group] if page else None,
        "active_nav": "wizard",
        "post_url": (
            subpage_post_url(ticker, page.slug, subpage.slug)
            if page is not None and subpage is not None
            else None
        ),
    }


def _subpage_template(page_slug: str, subpage_slug: str) -> str:
    candidate = f"wizard/{page_slug}/{subpage_slug}.html"
    try:
        templates.env.get_template(candidate)
    except TemplateNotFound:
        return "wizard/not_implemented.html"
    return candidate


@router.get("/wizard")
def wizard_ticker_redirect(ticker: str) -> RedirectResponse:
    symbol = _normalize_ticker(ticker)
    if not symbol:
        raise HTTPException(status_code=400, detail="Ticker is required")
    return RedirectResponse(url=f"/wizard/{symbol}", status_code=303)


@router.get("/wizard/{ticker}", response_class=HTMLResponse)
def wizard_landing(request: Request, ticker: str) -> HTMLResponse:
    symbol = _normalize_ticker(ticker)
    return templates.TemplateResponse(
        request,
        "wizard/landing.html",
        _wizard_context(ticker=symbol),
    )


@router.get(
    "/wizard/{ticker}/{page_slug}",
    response_class=HTMLResponse,
    response_model=None,
)
def wizard_page(request: Request, ticker: str, page_slug: str) -> Response:
    page = get_page(page_slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown wizard page")

    symbol = _normalize_ticker(ticker)
    subpage = first_subpage(page)
    if subpage is None:
        return templates.TemplateResponse(
            request,
            "wizard/not_implemented.html",
            _wizard_context(ticker=symbol, page=page),
        )
    return RedirectResponse(
        url=f"/wizard/{symbol}/{page.slug}/{subpage.slug}",
        status_code=307,
    )


@router.get(
    "/wizard/{ticker}/{page_slug}/{subpage_slug}",
    response_class=HTMLResponse,
)
def wizard_subpage(
    request: Request,
    ticker: str,
    page_slug: str,
    subpage_slug: str,
    period: str = "annual",
    exchange: str = "NASDAQ",
) -> HTMLResponse:
    page = get_page(page_slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown wizard page")
    subpage = get_subpage(page_slug, subpage_slug)
    if subpage is None:
        raise HTTPException(status_code=404, detail="Unknown wizard sub-page")

    symbol = _normalize_ticker(ticker)
    template_name = _subpage_template(page.slug, subpage.slug)
    logger.debug("Rendering wizard template %s", template_name)
    return templates.TemplateResponse(
        request,
        template_name,
        _wizard_context(ticker=symbol, page=page, subpage=subpage)
        | subpage.context_builder(symbol, period, exchange.upper().strip()),
    )


@router.post("/wizard/{ticker}/{page_slug}/{subpage_slug}")
async def wizard_subpage_post(
    request: Request,
    ticker: str,
    page_slug: str,
    subpage_slug: str,
) -> dict[str, Any]:
    from src.web.wizard_registry import get_subpage

    subpage = get_subpage(page_slug, subpage_slug)
    if subpage is None:
        raise HTTPException(status_code=404, detail="Unknown wizard sub-page")
    if subpage.post_handler is None:
        raise HTTPException(status_code=404, detail="POST not supported for this sub-page")

    symbol = _normalize_ticker(ticker)
    if not symbol:
        raise HTTPException(status_code=400, detail="Ticker is required")

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    try:
        return subpage.post_handler(symbol, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
