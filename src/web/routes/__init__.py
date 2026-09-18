"""Route package for HTML views."""

from __future__ import annotations

from fastapi import APIRouter

from src.web.routes import screener, statements, wizard

api_router = APIRouter()
api_router.include_router(statements.router)
api_router.include_router(screener.router)
api_router.include_router(wizard.router)
