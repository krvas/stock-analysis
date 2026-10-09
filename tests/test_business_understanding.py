"""Business Understanding › One-line Answers: context builder and page (no LLM)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.ai_tools.task import AiResult
from src.ai_tools.tasks.one_line_answers import (
    ONE_LINE_ANSWERS_TASK,
    Answer,
    OneLineAnswers,
)
from src.web.app import app
from src.web.routes.wizard_pages import business_understanding

URL = "/wizard/TEST/business-understanding/one-line-answers"


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
    answers = business_understanding.one_line_answers_context("TEST", "annual")[
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
    assert business_understanding.one_line_answers_context("TEST", "annual") == {
        "ai_pending": True
    }


def test_page_views(ready):
    client = TestClient(app)
    summary = client.get(URL, params={"view": "summary"}).text
    assert "industry answer" in summary
    assert "commodity answer" in summary
    assert "industry justification" not in summary

    detailed = client.get(URL, params={"view": "detailed"}).text
    assert "industry justification" in detailed
    assert "FY2025 10-K, Item 1 (Business)" in detailed

    bogus = client.get(URL, params={"view": "bogus"}).text
    assert '<option value="standard" selected>' in bogus
    assert "industry justification" not in bogus


def test_page_pending(monkeypatch):
    monkeypatch.setattr(
        business_understanding, "run_task", lambda task, ticker: AiResult("pending")
    )
    assert "AI answers are being generated" in TestClient(app).get(URL).text
