"""OpenRouter backend: a minimal tool-calling agent loop over the workspace.

The model gets ``list_files`` / ``read_file`` / ``grep`` tools confined to the
ticker's workspace (all its filings) and must finish with a JSON answer matching the task's
schema. Synchronous; one HTTP call per turn, at most ``AI_MAX_TURNS`` turns.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from src.ai_tools.task import AiTask
from src.ai_tools.workspace import WORKSPACE_LAYOUT
from src.config import (
    AI_MAX_TURNS,
    AI_MODELS_PATH,
    OPENROUTER_BASE_URL,
    load_project_dotenv,
)

logger = logging.getLogger(__name__)

_READ_LIMIT = 400  # default lines per read_file call
_GREP_MAX_MATCHES = 100
_HTTP_TIMEOUT_S = 300

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the workspace files with their line counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read lines of a workspace file (0-based offset).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "Case-insensitive regex search; returns file:line: text. "
                "Optional path limits it to one workspace file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
        },
    },
]


def resolve_in_workspace(workspace: Path, path: str) -> Path:
    """``path`` resolved inside ``workspace``; ``ValueError`` if it escapes."""
    root = workspace.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"path {path!r} is outside the workspace")
    return target


def list_files(workspace: Path) -> str:
    lines = []
    for path in sorted(workspace.resolve().rglob("*")):
        if path.is_file():
            count = len(path.read_text(encoding="utf-8").splitlines())
            lines.append(f"{path.relative_to(workspace.resolve())} ({count} lines)")
    return "\n".join(lines)


def read_file(
    workspace: Path, path: str, offset: int = 0, limit: int = _READ_LIMIT
) -> str:
    lines = resolve_in_workspace(workspace, path).read_text(encoding="utf-8")
    start = max(0, offset)
    return "\n".join(lines.splitlines()[start : start + max(1, limit)])


def grep(workspace: Path, pattern: str, path: str = ".") -> str:
    root = workspace.resolve()
    target = resolve_in_workspace(workspace, path)
    files = sorted(target.rglob("*")) if target.is_dir() else [target]
    regex = re.compile(pattern, re.IGNORECASE)
    matches = []
    for file in (f for f in files if f.is_file()):
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines()):
            if regex.search(line):
                matches.append(f"{file.relative_to(root)}:{number}: {line}")
                if len(matches) >= _GREP_MAX_MATCHES:
                    return "\n".join([*matches, "(truncated)"])
    return "\n".join(matches) or "no matches"


def _run_tool(workspace: Path, name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments or "{}")
        if name == "list_files":
            return list_files(workspace)
        if name == "read_file":
            return read_file(workspace, **args)
        if name == "grep":
            return grep(workspace, **args)
        return f"error: unknown tool {name!r}"
    except (ValueError, TypeError, OSError, re.error) as exc:
        return f"error: {exc}"


def _model_for(task: AiTask) -> str:
    models = json.loads(AI_MODELS_PATH.read_text(encoding="utf-8"))
    return models.get(task.name, models["default"])


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    load_project_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set.")
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def _system_prompt(task: AiTask, ticker: str) -> str:
    return (
        f"You are analysing {ticker.upper()}'s latest annual reports (10-Ks). "
        "Their sections are markdown files in your workspace; use the tools to "
        f"read them. {WORKSPACE_LAYOUT}\n\n"
        f"Task:\n{task.instructions}\n\n"
        "When done, reply with only a JSON object (no prose) matching this "
        f"JSON schema:\n{task.result_schema()}"
    )


def answer[T: BaseModel](
    task: AiTask[T], workspace: Path, ticker: str, accessions: list[str]
) -> T | None:
    """Run the agent loop; the validated answer, or ``None`` if it failed.

    ``accessions`` is unused: the workspace subfolder names already carry them.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(task, ticker)},
        {"role": "user", "content": "Read the workspace and answer the task."},
    ]
    model = _model_for(task)
    for _ in range(AI_MAX_TURNS):
        reply = _post_chat({"model": model, "messages": messages, "tools": _TOOLS})
        message = reply["choices"][0]["message"]
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            try:
                return task.parse(message.get("content") or "")
            except ValidationError as exc:
                logger.warning(
                    "%s %s: invalid final answer: %s", ticker, task.name, exc
                )
                return None
        for call in tool_calls:
            function = call["function"]
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": _run_tool(
                        workspace, function["name"], function.get("arguments", "")
                    ),
                }
            )
    logger.warning("%s %s: no answer after %d turns", ticker, task.name, AI_MAX_TURNS)
    return None
