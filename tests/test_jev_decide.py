"""Jev decisions: each kind's hard rules, its fallback, and the decision log."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import src.config
from scripts import jev_decide as jd


@pytest.fixture(autouse=True)
def default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the tunables so a JEV_* override in .env cannot move these tests."""
    monkeypatch.setattr(jd, "FINDINGS_MARGIN", 0.15)
    monkeypatch.setattr(jd, "COMMENTS_MIN_PROBABILITY", 0.6)
    monkeypatch.setattr(jd, "EFFORT_MIN_CONFIDENCE", 0.5)
    monkeypatch.setattr(jd, "ARENA_EXCLUDE", 0.85)


@pytest.fixture(autouse=True)
def log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "logs" / "decisions.jsonl"
    monkeypatch.setattr(jd, "LOG_PATH", path)
    return path


def jev_returns(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> list:
    """Stub the API with ``answers``; returns the list of calls it received."""
    calls: list[tuple[dict, dict]] = []

    def fake(state: dict, questions: dict, key: str) -> dict[str, Any]:
        calls.append((state, questions))
        return answers

    monkeypatch.setattr(jd, "_call_jev", fake)
    return calls


def jev_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object) -> dict[str, Any]:
        raise jd.JevError("HTTP 401")

    monkeypatch.setattr(jd, "_call_jev", boom)


def choice(label: str, p: float, confidence: float = 0.9) -> dict[str, Any]:
    return {"choice": label, "probabilities": {label: p}, "confidence": confidence}


def decisions(out: dict[str, Any]) -> list[str]:
    return [r["decision"] for r in out["results"]]


# findings

FINDINGS = {
    "findings": [
        {"id": 1, "needs_user_decision": False},
        {"id": 2, "needs_user_decision": False},
        {"id": 3, "needs_user_decision": True},
    ],
    "intent_notes": "notes",
}


@pytest.mark.parametrize(
    ("finding", "score", "decision"),
    [
        ({"id": 1}, 0.85, "execute"),
        ({"id": 1}, 0.8499, "human"),
        ({"id": 1}, 0.1501, "human"),
        ({"id": 1}, 0.15, "drop"),
        ({"id": 1}, None, "human"),
        ({"id": 1, "needs_user_decision": True}, 0.99, "human"),
        ({"id": 1, "needs_user_decision": True}, 0.05, "human"),
    ],
)
def test_finding_thresholds(finding: dict, score: float | None, decision: str) -> None:
    answer = None if score is None else {"noul": score}
    assert jd.KINDS["findings"].decide(finding, answer)[0] == decision


def test_one_margin_sets_both_finding_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEV_FINDINGS_MARGIN", "0.3")
    reloaded = importlib.reload(jd)
    try:
        decide = reloaded.KINDS["findings"].decide
        assert decide({"id": 1}, {"noul": 0.7})[0] == "execute"
        assert decide({"id": 1}, {"noul": 0.3})[0] == "drop"
        assert decide({"id": 1}, {"noul": 0.69})[0] == "human"
    finally:
        monkeypatch.delenv("JEV_FINDINGS_MARGIN")
        importlib.reload(jd)


def test_findings_scored_and_decided(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_returns(
        monkeypatch, {"1": {"noul": 0.9}, "2": {"noul": 0.1}, "3": {"noul": 0.99}}
    )
    out = jd.run("findings", FINDINGS, "key")
    assert out["api_status"] == "ok"
    assert decisions(out) == ["execute", "drop", "human"]
    assert out["results"][2]["reason"] == "needs_user_decision"


def test_findings_missing_key_go_to_the_human() -> None:
    out = jd.run("findings", FINDINGS, None)
    assert "missing" in out["api_status"]
    assert set(decisions(out)) == {"human"}


def test_findings_api_failure_go_to_the_human(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_fails(monkeypatch)
    out = jd.run("findings", FINDINGS, "key")
    assert out["api_status"].startswith("error: HTTP 401")
    assert set(decisions(out)) == {"human"}


def test_findings_load_intent_notes_beside_input(tmp_path: Path) -> None:
    (tmp_path / "findings-1.json").write_text('[{"id": 1}]', encoding="utf-8")
    (tmp_path / "intent-a.md").write_text("keep X", encoding="utf-8")
    payload = jd.KINDS["findings"].load(tmp_path / "findings-1.json")
    assert payload == {"findings": [{"id": 1}], "intent_notes": "keep X"}


# comments

HUMAN = {"id": "h1", "author": "pat", "bot": False, "body": "rename foo to bar"}
BOT = {"id": "b1", "author": "bugbot", "bot": True, "body": "unused export"}
BOT_AUTH = {"id": "b2", "author": "bugbot", "bot": True, "body": "Missing auth check"}


@pytest.mark.parametrize(
    ("comment", "answer", "decision"),
    [
        (HUMAN, choice("mechanical", 0.9), "mechanical"),
        (HUMAN, choice("mechanical", 0.59), "judgment"),
        (BOT, choice("dismiss", 0.9), "dismiss"),
        (BOT, choice("dismiss", 0.5), "ask"),
        (BOT, choice("fix", 0.5), "ask"),
        (BOT_AUTH, choice("dismiss", 0.99), "ask"),
        (BOT_AUTH, choice("fix", 0.9), "fix"),
        ({**BOT, "body": "possible data loss on retry"}, choice("dismiss", 0.9), "ask"),
        ({**BOT, "body": "author field unused"}, choice("dismiss", 0.9), "dismiss"),
    ],
)
def test_comment_rules(comment: dict, answer: dict, decision: str) -> None:
    assert jd.KINDS["comments"].decide(comment, answer)[0] == decision


def test_comments_fall_back_conservatively(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_fails(monkeypatch)
    assert decisions(jd.run("comments", [HUMAN, BOT], "key")) == ["judgment", "ask"]


def test_comments_offer_labels_by_author_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = jev_returns(monkeypatch, {})
    jd.run("comments", [HUMAN, BOT], "key")
    questions = calls[0][1]
    assert set(questions["h1"]["criteria"]) == {"mechanical", "judgment"}
    assert set(questions["b1"]["criteria"]) == {"fix", "dismiss", "ask"}


# playbook

REQUEST = {"request": "the page crashes on save", "agent_choice": "bug-fix"}


def test_playbook_never_sends_agent_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = jev_returns(monkeypatch, {"request": choice("feature", 0.8)})
    jd.run("playbook", REQUEST, "key")
    state, _questions = calls[0]
    assert state == {"request": REQUEST["request"]}


def test_playbook_keeps_agent_choice_when_jev_disagrees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jev_returns(monkeypatch, {"request": choice("feature", 0.8)})
    [result] = jd.run("playbook", REQUEST, "key")["results"]
    assert result["decision"] == "bug-fix"
    assert result["jev_choice"] == "feature"
    assert result["agree"] is False
    assert result["advisory"] is True


def test_playbook_fallback_is_agent_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_fails(monkeypatch)
    [result] = jd.run("playbook", REQUEST, "key")["results"]
    assert result["decision"] == "bug-fix"
    assert result["jev_choice"] is None


# effort


@pytest.mark.parametrize(
    ("answer", "decision"),
    [
        (choice("low", 0.7, confidence=0.5), "low"),
        (choice("low", 0.7, confidence=0.49), "session"),
        (None, "session"),
    ],
)
def test_effort_rules(answer: dict | None, decision: str) -> None:
    assert jd.KINDS["effort"].decide({"brief": "x"}, answer)[0] == decision


def test_effort_never_offers_max(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = jev_returns(monkeypatch, {})
    jd.run("effort", {"brief": "x"}, "key")
    assert "max" not in calls[0][1]["brief"]["criteria"]


def test_effort_fallback_is_session(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_fails(monkeypatch)
    assert decisions(jd.run("effort", {"brief": "rename a var"}, "key")) == ["session"]


# arena

CANDIDATES = [{"id": "a", "report": "tests fail"}, {"id": "b", "report": "ok"}]


def test_arena_excludes_only_obviously_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_returns(monkeypatch, {"a": {"noul": 0.9}, "b": {"noul": 0.84}})
    assert decisions(jd.run("arena", CANDIDATES, "key")) == ["exclude", "keep"]


def test_arena_never_excludes_everyone(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_returns(monkeypatch, {"a": {"noul": 0.9}, "b": {"noul": 0.95}})
    out = jd.run("arena", CANDIDATES, "key")
    assert decisions(out) == ["keep", "keep"]
    assert all("keeping all" in r["reason"] for r in out["results"])


def test_arena_fallback_keeps(monkeypatch: pytest.MonkeyPatch) -> None:
    jev_fails(monkeypatch)
    assert decisions(jd.run("arena", CANDIDATES, "key")) == ["keep", "keep"]


# log


def test_log_gets_one_line_per_result(
    monkeypatch: pytest.MonkeyPatch, log_path: Path
) -> None:
    jev_returns(monkeypatch, {"a": {"noul": 0.1}, "b": {"noul": 0.2}})
    jd.run("arena", CANDIDATES, "key")
    jd.run("playbook", REQUEST, None)
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [(line["kind"], line["id"]) for line in lines] == [
        ("arena", "a"),
        ("arena", "b"),
        ("playbook", "request"),
    ]
    assert lines[0]["answer"] == {"noul": 0.1}
    assert lines[2]["agent_choice"] == "bug-fix"
    assert "agree" in lines[2]


# cli


def test_help_lists_every_kind(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        jd.main(["jev_decide.py", "--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert all(f"  {name}: " in out for name in jd.KINDS)


def test_every_tunable_reads_the_environment() -> None:
    """A module-level number in jev_decide.py must come from ``_setting``."""
    source = Path(jd.__file__).read_text(encoding="utf-8")
    hardcoded = [
        target.id
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and type(node.value.value) in (int, float)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    assert not hardcoded, (
        f"{hardcoded} in scripts/jev_decide.py: read each tunable with "
        '_setting("<NAME>", "<default>") at the top of the file so .env can '
        "override it as JEV_<NAME>."
    )


# decision log


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_a_run_from_a_worktree_logs_to_the_main_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree's logs/ is deleted with it, so the log lives in the main checkout.

    ``git rebase -x`` exports GIT_DIR; the log must not follow it. Pointing it
    at a throwaway repo keeps a failure from writing to this repo's log."""
    main = tmp_path / "main"
    other = tmp_path / "other"
    for repo in (main, other):
        repo.mkdir()
        _git(repo, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "root")
    worktree = main / ".claude" / "worktrees" / "w"
    _git(main, "worktree", "add", "-q", str(worktree))
    monkeypatch.setattr(src.config, "PROJECT_ROOT", worktree)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    try:
        reloaded = importlib.reload(jd)
        reloaded.run("findings", {"findings": [{"id": 1}], "intent_notes": ""}, None)
    finally:
        monkeypatch.undo()
        importlib.reload(jd)
    logged = main / "logs" / "jev" / "decisions.jsonl"
    assert json.loads(logged.read_text())["decision"] == "human"
    assert not (worktree / "logs").exists()
    assert not (other / "logs").exists()


# the jev skill's triggers


def test_skill_description_leads_with_the_missed_triggers() -> None:
    """The orchestrator never loaded the skill: about 20 playbook picks for
    delegates went unlogged. The triggers it missed open the description."""
    skill = Path(jd.__file__).parents[1] / ".claude" / "skills" / "jev" / "SKILL.md"
    frontmatter, body = skill.read_text(encoding="utf-8").split("---\n")[1:3]
    description = frontmatter.split("description:", 1)[1].strip()
    assert description.startswith(
        "Use after picking a pstack playbook (for yourself or a delegate)"
    )
    first_sentence = description.split(". ")[0]
    assert "when briefing a delegate that triages review findings" in first_sentence
    body = " ".join(body.split())
    assert "Jev is unavailable" in body and "scripts/jev_decide.py" in body
