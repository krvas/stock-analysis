"""Business Understanding › One-line Answers: context builder (no LLM)."""

from __future__ import annotations

import json

import pytest

from src.ai_tools.task import AiResult
from src.ai_tools.tasks.one_line_answers import (
    ONE_LINE_ANSWERS_TASK,
    Answer,
    OneLineAnswers,
)
from src.web.routes.wizard_pages import business_understanding
from src.web.settings import Settings, resolve
from src.web.wizard_registry import get_subpage


def _settings(**values: object) -> Settings:
    decl = get_subpage("business-understanding", "one-line-answers").settings
    return resolve(json.dumps(values), decl)


def _answers() -> OneLineAnswers:
    def answer(name: str) -> Answer:
        return Answer(
            answer=f"{name} answer",
            justification=f"{name} justification",
            source="FY2025 10-K, Item 1 (Business)",
        )

    return OneLineAnswers(
        **{name: answer(name) for name in OneLineAnswers.model_fields}
    )


@pytest.fixture
def ready(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_task(task, ticker):
        assert task is ONE_LINE_ANSWERS_TASK
        return AiResult("ready", _answers())

    monkeypatch.setattr(business_understanding, "run_task", fake_run_task)


def test_every_question_has_a_description():
    for field in OneLineAnswers.model_fields.values():
        assert field.description


def test_context_ready_lists_answers_in_field_order(ready):
    answers = business_understanding.one_line_answers_context("TEST", _settings())[
        "answers"
    ]
    fields = OneLineAnswers.model_fields
    assert [item["question"] for item in answers] == [
        field.description for field in fields.values()
    ]
    assert answers[0]["answer"] == "industry answer"
    assert answers[0]["source"] == "FY2025 10-K, Item 1 (Business)"


def test_context_pending(monkeypatch):
    monkeypatch.setattr(
        business_understanding, "run_task", lambda task, ticker: AiResult("pending")
    )
    assert business_understanding.one_line_answers_context("TEST", _settings()) == {
        "ai_pending": True
    }


@pytest.mark.parametrize("view", ["summary", "standard", "detailed"])
def test_context_carries_the_view(ready, view):
    ctx = business_understanding.one_line_answers_context("TEST", _settings(view=view))
    assert ctx["view"] == view
