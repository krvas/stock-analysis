"""``run_task``: answer an :class:`AiTask` from a ticker's latest 10-Ks.

Flow: one EDGAR lookup of the latest ``AI_ANNUAL_REPORTS`` 10-Ks → cached
answer if it was computed from those same filings → else build the ticker's
workspace (one subfolder per filing) and ask the backend chosen by
``AI_BACKEND``. Validated answers are cached at
``AI_CACHE_DIR/{TICKER}/{task}.json`` with the accessions they were built from
(when ``AI_CACHE_ENABLED``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from src.ai_tools import claude_code, openrouter
from src.ai_tools.task import AiResult, AiTask
from src.ai_tools.workspace import build_workspace, latest_10ks
from src.config import AI_CACHE_DIR, AiBackend, ai_backend, ai_cache_enabled

logger = logging.getLogger(__name__)

# (task, workspace, ticker, accessions) -> validated answer, or None while
# pending (or after a failed attempt).
BACKENDS: dict[
    AiBackend, Callable[[AiTask, Path, str, list[str]], BaseModel | None]
] = {
    "claude_code": claude_code.answer,
    "openrouter": openrouter.answer,
}


def cache_path(task: AiTask, ticker: str) -> Path:
    return AI_CACHE_DIR / ticker.upper() / f"{task.name}.json"


def run_task[T: BaseModel](task: AiTask[T], ticker: str) -> AiResult[T]:
    """The task's answer for ``ticker``'s latest 10-Ks, or ``pending``."""
    filings = latest_10ks(ticker)
    accessions = [filing.accession_number for filing in filings]
    cache_enabled = ai_cache_enabled()
    cached = cache_path(task, ticker)
    if cache_enabled and cached.is_file():
        entry = json.loads(cached.read_text(encoding="utf-8"))
        if entry["accessions"] == accessions:
            return AiResult("ready", task.result_model.model_validate(entry["answer"]))

    workspace = build_workspace(ticker, filings)
    answer = BACKENDS[ai_backend()](task, workspace, ticker, accessions)
    if answer is None:
        return AiResult("pending")
    if cache_enabled:
        cached.parent.mkdir(parents=True, exist_ok=True)
        entry = {"accessions": accessions, "answer": answer.model_dump(mode="json")}
        cached.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return AiResult("ready", answer)
