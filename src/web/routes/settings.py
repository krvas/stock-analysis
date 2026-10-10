"""Settings over HTTP: the only module that knows the Settings cookies."""

from __future__ import annotations

from typing import Final

from fastapi import Request

from src.web.settings import Settings, SettingsDecl, resolve

_SETTINGS_COOKIE: Final = "settings"


def settings_for(request: Request, decl: SettingsDecl) -> Settings:
    return resolve(request.cookies.get(_SETTINGS_COOKIE), decl)
