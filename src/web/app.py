"""FastAPI application entrypoint.

Run locally::

    uvicorn src.web.app:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.config import load_project_dotenv
from src.web.routes import api_router
from src.web.templating import STATIC_DIR


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_project_dotenv()
    yield


app = FastAPI(
    title="Stock Analysis",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "statements": "/statements/{ticker}",
        "wizard": "/wizard/{ticker}",
        "screener": "/screener",
        "docs": "/docs",
    }
