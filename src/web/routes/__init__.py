"""Route package for HTML views."""

from fastapi import APIRouter

from src.web.routes import screener, statements

api_router = APIRouter()
api_router.include_router(statements.router)
api_router.include_router(screener.router)
