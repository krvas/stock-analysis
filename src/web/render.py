"""Render a page with its resolved Settings and the Settings drawer.

Shared by the wizard and statements routers; ``routes/settings.py`` owns the
POST that writes the cookies named here.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.web.page_types import NavContext
from src.web.settings import (
    Settings,
    SettingsDecl,
    build_drawer,
    known_refusal,
    resolve,
)
from src.web.templating import templates

SETTINGS_COOKIE: Final = "settings"
ERROR_COOKIE: Final = "settings_error"


def settings_for(request: Request, decl: SettingsDecl) -> Settings:
    return resolve(request.cookies.get(SETTINGS_COOKIE), decl)


def render_with_settings(
    request: Request,
    template: str,
    context: dict[str, Any],
    *,
    settings: Settings,
    nav: NavContext,
) -> HTMLResponse:
    raw_error = request.cookies.get(ERROR_COOKIE)
    drawer = build_drawer(
        settings, next_path=request.url.path, error=known_refusal(raw_error)
    )
    response = templates.TemplateResponse(
        request, template, context | {"nav": nav, "drawer": drawer}
    )
    if raw_error is not None:
        response.delete_cookie(
            ERROR_COOKIE, path=request.url.path, httponly=True, samesite="lax"
        )
    return response
