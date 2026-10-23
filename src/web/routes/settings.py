from __future__ import annotations

from typing import Final
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.config import SETTINGS_COOKIE_MAX_AGE
from src.web.render import ERROR_COOKIE, SETTINGS_COOKIE
from src.web.settings import SETTINGS, Refused, Saved, apply_submission

router = APIRouter(tags=["settings"])

_ERROR_COOKIE_MAX_AGE: Final = 60
_MAX_BODY_BYTES: Final = 8 * 1024
_MAX_FORM_FIELDS: Final = len(SETTINGS) + 8


def _is_cross_site(request: Request) -> bool:
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site not in ("same-origin", "none")
    origin = request.headers.get("origin")
    return origin is not None and urlsplit(origin).netloc != request.headers.get("host")


async def _read_urlencoded_scalars(request: Request) -> dict[str, str]:
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Settings form too large")
    try:
        pairs = parse_qsl(
            body.decode("utf-8", errors="replace"),
            keep_blank_values=True,
            max_num_fields=_MAX_FORM_FIELDS,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Too many form fields") from None
    return dict(pairs)


@router.post("/settings")
async def save_settings(request: Request) -> RedirectResponse:
    if _is_cross_site(request):
        raise HTTPException(status_code=403, detail="Cross-site settings change")
    form = await _read_urlencoded_scalars(request)
    outcome = apply_submission(form, request.cookies.get(SETTINGS_COOKIE))
    response = RedirectResponse(outcome.redirect_to, status_code=303)
    secure = request.url.scheme == "https"
    match outcome:
        case Saved(cookie_value=value):
            response.set_cookie(
                SETTINGS_COOKIE,
                value,
                max_age=SETTINGS_COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
                secure=secure,
            )
        case Refused(message=message):
            target = urlsplit(outcome.redirect_to).path
            if target != "/":
                response.set_cookie(
                    ERROR_COOKIE,
                    message,
                    max_age=_ERROR_COOKIE_MAX_AGE,
                    path=target,
                    httponly=True,
                    samesite="lax",
                    secure=secure,
                )
    return response
