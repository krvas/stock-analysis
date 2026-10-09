"""Claude Code backend: hand a task off through request/response files.

On a miss :func:`answer` writes ``AI_REQUESTS_DIR/{TICKER}__{task}.json``
(with the accessions of the filings in the workspace); a Claude Code session
(see :mod:`src.ai_tools.pending`) reads the workspace and writes the JSON
answer to the request's ``response_path``. The next call with the same
accessions validates that response, removes both files, and returns the answer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from src.ai_tools.task import AiTask
from src.ai_tools.workspace import WORKSPACE_LAYOUT
from src.config import AI_REQUESTS_DIR

logger = logging.getLogger(__name__)

RESPONSE_SUFFIX = ".response.json"


def request_path(task: AiTask, ticker: str) -> Path:
    """Request file for (ticker, task); fixed so refreshes reuse it."""
    return AI_REQUESTS_DIR / f"{ticker.upper()}__{task.name}.json"


def response_path(request: Path) -> Path:
    return request.with_name(request.name.removesuffix(".json") + RESPONSE_SUFFIX)


def answer[T: BaseModel](
    task: AiTask[T], workspace: Path, ticker: str, accessions: list[str]
) -> T | None:
    """The validated response if one was written, else ``None`` (pending).

    A response counts only while its request names the same ``accessions``;
    when the latest filings change, the request is rewritten and any response
    to the old one is discarded.
    """
    request = request_path(task, ticker)
    response = response_path(request)
    if request.is_file():
        stored = json.loads(request.read_text(encoding="utf-8"))["accessions"]
        if stored != accessions:
            logger.info("Filings changed for %s, rewriting request", request)
            request.unlink()
    if not request.is_file():
        response.unlink(missing_ok=True)
        _write_request(request, response, task, workspace, ticker, accessions)
        return None
    if response.is_file():
        try:
            result = task.parse(response.read_text(encoding="utf-8"))
        except ValidationError as exc:
            logger.warning("Invalid response %s, discarding: %s", response, exc)
            response.unlink()
        else:
            response.unlink()
            request.unlink()
            return result
    return None


def _write_request(
    request: Path,
    response: Path,
    task: AiTask,
    workspace: Path,
    ticker: str,
    accessions: list[str],
) -> None:
    payload = {
        "ticker": ticker.upper(),
        "task": task.name,
        "accessions": accessions,
        "instructions": task.instructions,
        "workspace_layout": WORKSPACE_LAYOUT,
        "result_schema": task.result_model.model_json_schema(),
        "workspace": str(workspace.resolve()),
        "response_path": str(response.resolve()),
    }
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote Claude Code request %s", request)
