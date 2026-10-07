"""The triage gate: threshold, hard exclusion, and fallback when Jev fails."""

from __future__ import annotations

import pytest

from scripts import triage_findings as tf

FINDINGS = [
    {"id": 1, "needs_user_decision": False},
    {"id": 2, "needs_user_decision": False},
    {"id": 3, "needs_user_decision": True},
]


@pytest.mark.parametrize(
    ("finding", "score", "decision"),
    [
        ({"id": 1}, 0.85, "execute"),
        ({"id": 1}, 0.8499, "human"),
        ({"id": 1}, None, "human"),
        ({"id": 1, "needs_user_decision": True}, 0.99, "human"),
    ],
)
def test_decide(finding: dict, score: float | None, decision: str) -> None:
    assert tf.decide(finding, score)[0] == decision


def test_triage_scores_and_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tf, "_call_jev", lambda state, questions, key: {"1": 0.9, "2": 0.4, "3": 0.99}
    )
    out = tf.triage(FINDINGS, "notes", "key")
    assert out["api_status"] == "ok"
    assert [r["decision"] for r in out["results"]] == ["execute", "human", "human"]
    assert out["results"][2]["reason"] == "needs_user_decision"


def test_missing_key_sends_everything_to_the_human() -> None:
    out = tf.triage(FINDINGS, "notes", None)
    assert "missing" in out["api_status"]
    assert {r["decision"] for r in out["results"]} == {"human"}


def test_api_failure_sends_everything_to_the_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object) -> dict[str, float]:
        raise tf.TriageError("HTTP 401")

    monkeypatch.setattr(tf, "_call_jev", boom)
    out = tf.triage(FINDINGS, "notes", "key")
    assert out["api_status"].startswith("error: HTTP 401")
    assert {r["decision"] for r in out["results"]} == {"human"}
