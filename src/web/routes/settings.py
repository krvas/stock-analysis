from __future__ import annotations

from typing import Any, Final
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.config import SETTINGS_COOKIE_MAX_AGE
from src.web.page_types import NavContext
from src.web.settings import (
    Refused,
    Saved,
    Settings,
    SettingsDecl,
    apply_submission,
    build_drawer,
    resolve,
)
from src.web.templating import templates

router = APIRouter(tags=["settings"])

_SETTINGS_COOKIE: Final = "settings"
_ERROR_COOKIE: Final = "settings_error"
_ERROR_COOKIE_MAX_AGE: Final = 60


def settings_for(request: Request, decl: SettingsDecl) -> Settings:
    return resolve(request.cookies.get(_SETTINGS_COOKIE), decl)


def render_with_settings(
    request: Request,
    template: str,
    context: dict[str, Any],
    *,
    settings: Settings,
    nav: NavContext,
) -> HTMLResponse:
    error = request.cookies.get(_ERROR_COOKIE)
    drawer = build_drawer(settings, next_path=request.url.path, error=error)
    response = templates.TemplateResponse(
        request, template, context | {"nav": nav, "drawer": drawer}
    )
    if error is not None:
        response.delete_cookie(_ERROR_COOKIE, path="/", httponly=True, samesite="lax")
    return response


@router.post("/settings")
async def save_settings(request: Request) -> RedirectResponse:
    # Parsed by hand: request.form() needs python-multipart, and the drawer
    # only posts a few urlencoded scalars. Last value wins.
    body = (await request.body()).decode("utf-8", errors="replace")
    form = dict(parse_qsl(body, keep_blank_values=True))
    outcome = apply_submission(form, request.cookies.get(_SETTINGS_COOKIE))
    response = RedirectResponse(outcome.redirect_to, status_code=303)
    match outcome:
        case Saved(cookie_value=value):
            response.set_cookie(
                _SETTINGS_COOKIE,
                value,
                max_age=SETTINGS_COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
            )
        case Refused(message=message):
            response.set_cookie(
                _ERROR_COOKIE,
                message,
                max_age=_ERROR_COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
            )
    return response
