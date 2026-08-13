"""Shared Jinja2 template configuration for FastAPI routes."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

SRC_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SRC_DIR / "templates"
STATIC_DIR = SRC_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
