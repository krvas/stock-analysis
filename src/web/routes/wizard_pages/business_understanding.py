"""Business Understanding wizard sub-pages: context builders."""

from __future__ import annotations

from typing import Any

from src.ai_tools.runner import run_task
from src.ai_tools.tasks.one_line_answers import ONE_LINE_ANSWERS_TASK


def one_line_answers_context(ticker: str, period: str) -> dict[str, Any]:
    """Each question (field description) with its AI answer, in field order."""
    result = run_task(ONE_LINE_ANSWERS_TASK, ticker)
    if result.answer is None:
        return {"ai_pending": True}
    fields = type(result.answer).model_fields
    return {
        "answers": [
            {"question": fields[name].description} | value.model_dump()
            for name, value in result.answer
        ]
    }
