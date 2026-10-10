"""Central configuration: paths, retention, and database location."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal, cast, get_args

from dotenv import load_dotenv

from src.models.statement import PeriodType

logger = logging.getLogger(__name__)

_dotenv_loaded = False

# Project root is two levels above src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DUCKDB_DIR = DATA_DIR / "duckdb"

# Default DuckDB file path
DEFAULT_DB_PATH = DUCKDB_DIR / "indian_stocks.duckdb"
DEFAULT_WIZARD_DB_PATH = DUCKDB_DIR / "wizard.duckdb"

# Schema SQL files
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "database" / "schema.sql"
WIZARD_SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "database" / "wizard.sql"

# Historical data retention target (years)
HISTORY_YEARS = 10

# edgartools local filing cache (LRU by company)
EDGARTOOLS_CACHE_DIR = DATA_DIR / "edgartools_cache"
# Keep this many most recently viewed companies; older ones are deleted.
# Override with EDGARTOOLS_COMPANY_CACHE_SIZE env var when storage is tight.
EDGARTOOLS_COMPANY_CACHE_SIZE = max(
    1,
    int(os.environ.get("EDGARTOOLS_COMPANY_CACHE_SIZE", "10")),
)
# Refetch cached statements when the latest stored filing date is older than these.
EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS = max(
    1,
    int(os.environ.get("EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS", "3")),
)
EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS = max(
    1,
    int(os.environ.get("EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS", "12")),
)
# edgartools' own HTTP cache directories (under EDGARTOOLS_CACHE_DIR):
# once it is over this size, setup clears it completely (edgartools' clear_cache).
# Override with EDGARTOOLS_HTTP_CACHE_MAX_MB env var.
EDGARTOOLS_HTTP_CACHE_MAX_MB = max(
    1,
    int(os.environ.get("EDGARTOOLS_HTTP_CACHE_MAX_MB", "300")),
)
# Years of filing history cached per company: annual bundles hold up to this
# many 10-Ks, quarterly bundles up to 4x as many 10-Qs. Requests slice the
# periods they need from the cached bundle.
MAX_CACHE_YEARS = max(1, int(os.environ.get("MAX_CACHE_YEARS", "16")))
MAX_CACHE_QUARTERS = MAX_CACHE_YEARS * 4
# Most periods (and filings) cached per bundle, by period type.
MAX_PERIODS_BY_PERIOD: dict[PeriodType, int] = {
    "annual": MAX_CACHE_YEARS,
    "quarterly": MAX_CACHE_QUARTERS,
}

MAX_ITEMS_PER_SIDE = 10
SETTINGS_COOKIE_MAX_AGE = 365 * 24 * 60 * 60

# AI tools (src/ai_tools): 10-K section workspaces, validated-answer cache and
# Claude Code request handoff files, all under one directory.
AI_TOOLS_DIR = DATA_DIR / "ai_tools"
AI_WORKSPACE_DIR = AI_TOOLS_DIR / "workspace"
AI_CACHE_DIR = AI_TOOLS_DIR / "cache"
AI_REQUESTS_DIR = AI_TOOLS_DIR / "requests"
# Latest original 10-Ks one AI run reads together (one workspace subfolder each).
AI_ANNUAL_REPORTS = 5
# Which backend answers tasks and whether validated answers are cached are
# read from AI_BACKEND / AI_CACHE_ENABLED at call time (after .env is loaded):
# see ai_backend() / ai_cache_enabled() below.
AiBackend = Literal["claude_code", "openrouter"]
# Task name -> OpenRouter model id ("default" fallback); claude_code ignores it.
AI_MODELS_PATH = Path(__file__).resolve().parent / "ai_tools" / "models.json"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Most model turns (tool-call rounds) per OpenRouter task run.
AI_MAX_TURNS = max(1, int(os.environ.get("AI_MAX_TURNS", "20")))

# Logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "platform.log"

# Parquet partitioning hints (used by ingestion modules)
RAW_SUBDIRS = {
    "companies": RAW_DATA_DIR / "companies",
    "prices": RAW_DATA_DIR / "prices",
    "financials": RAW_DATA_DIR / "financials",
    "balance_sheets": RAW_DATA_DIR / "balance_sheets",
    "cash_flows": RAW_DATA_DIR / "cash_flows",
    "corporate_actions": RAW_DATA_DIR / "corporate_actions",
}


def load_project_dotenv() -> None:
    """Load ``.env`` from the project root once (no-op if already loaded)."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True

    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return

    try:
        load_dotenv(env_path)
    except (PermissionError, OSError) as exc:
        logger.warning(
            "Could not read %s (%s); using existing process environment",
            env_path,
            exc,
        )


def ai_backend() -> AiBackend:
    """``AI_BACKEND`` from the environment / ``.env`` (default ``claude_code``)."""
    load_project_dotenv()
    value = os.environ.get("AI_BACKEND", "claude_code").strip().lower()
    allowed = get_args(AiBackend)
    if value not in allowed:
        raise ValueError(f"AI_BACKEND must be one of {allowed}, not {value!r}")
    return cast(AiBackend, value)


def ai_cache_enabled() -> bool:
    """``AI_CACHE_ENABLED`` from the environment / ``.env`` (default true)."""
    load_project_dotenv()
    value = os.environ.get("AI_CACHE_ENABLED", "true").strip().lower()
    return value not in ("0", "false", "no", "off")
