"""FastAPI application entrypoint.

Run locally::

    uvicorn src.web.app:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.web.routes import api_router
from src.web.templating import STATIC_DIR

app = FastAPI(title="Stock Analysis", docs_url="/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "statements": "/statements/{ticker}",
        "screener": "/screener",
        "docs": "/docs",
    }
