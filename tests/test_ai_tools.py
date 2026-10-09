"""AI tools: workspace, run_task caching, Claude Code handoff, OpenRouter."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from src.ai_tools import claude_code, openrouter, runner, workspace
from src.ai_tools.task import AiResult, AiTask

ACCESSIONS = ["0000000000-24-000001", "0000000000-23-000001"]
FOLDER = f"2024_{ACCESSIONS[0]}"


class _Answer(BaseModel):
    summary: str


_TASK = AiTask(name="test_task", instructions="Summarise.", result_model=_Answer)


class _TenK(dict):
    """Like edgartools' TenK: a missing item reads as ``None``."""

    __getitem__ = dict.get


def _filings(accessions: list[str]) -> list[SimpleNamespace]:
    return [SimpleNamespace(accession_number=acc) for acc in accessions]


@pytest.fixture
def ai_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No network: fixed filings, a one-file workspace, dirs under tmp_path."""
    root = tmp_path / "workspace" / "TEST"
    (root / FOLDER).mkdir(parents=True)
    (root / FOLDER / "business.md").write_text("# Item 1\n\nWe sell widgets.\n")
    monkeypatch.setattr(runner, "AI_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(claude_code, "AI_REQUESTS_DIR", tmp_path / "requests")
    monkeypatch.setattr(runner, "latest_10ks", lambda ticker: _filings(ACCESSIONS))
    monkeypatch.setattr(runner, "build_workspace", lambda ticker, filings: root)
    monkeypatch.setattr(runner, "ai_cache_enabled", lambda: True)
    return root


def _use_backend(monkeypatch: pytest.MonkeyPatch, backend) -> None:
    monkeypatch.setattr(runner, "ai_backend", lambda: "claude_code")
    monkeypatch.setitem(runner.BACKENDS, "claude_code", backend)


def test_build_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "AI_WORKSPACE_DIR", tmp_path)
    parsed = []

    def filing(acc, period, filed):
        def obj():
            parsed.append(acc)
            return _TenK({"Item 1": "Widgets.", "Item 1A": "Risky.", "Item 7": " "})

        return SimpleNamespace(
            accession_number=acc, period_of_report=period, filing_date=filed, obj=obj
        )

    filings = [
        filing("A-1", "2024-09-28", dt.date(2024, 11, 1)),
        filing("A-2", None, dt.date(2023, 11, 3)),
    ]
    root = workspace.build_workspace("test", filings)
    assert root == tmp_path / "TEST"
    assert sorted(p.name for p in root.iterdir()) == ["2023_A-2", "2024_A-1"]
    folder = root / "2024_A-1"
    assert sorted(p.name for p in folder.iterdir()) == [
        "business.md",
        "market_risk.md",
        "mdna.md",
        "risk_factors.md",
    ]
    assert (folder / "business.md").read_text() == "# Item 1\n\nWidgets.\n"
    assert "unavailable" in (folder / "mdna.md").read_text()
    assert "unavailable" in (folder / "market_risk.md").read_text()

    workspace.build_workspace("TEST", filings)
    assert parsed == ["A-1", "A-2"]

    workspace.build_workspace("TEST", filings[:1])
    assert [p.name for p in root.iterdir()] == ["2024_A-1"]


def test_run_task_caches_answer(ai_env, monkeypatch):
    calls = []

    def backend(task, root, ticker, accessions):
        calls.append(accessions)
        return _Answer(summary="widgets")

    _use_backend(monkeypatch, backend)
    first = runner.run_task(_TASK, "TEST")
    assert first == AiResult("ready", _Answer(summary="widgets"))
    entry = json.loads(runner.cache_path(_TASK, "TEST").read_text())
    assert entry == {"accessions": ACCESSIONS, "answer": {"summary": "widgets"}}

    second = runner.run_task(_TASK, "TEST")
    assert second == first
    assert calls == [ACCESSIONS]


def test_run_task_cache_disabled(ai_env, monkeypatch):
    calls = []

    def backend(task, root, ticker, accessions):
        calls.append(ticker)
        return _Answer(summary="widgets")

    _use_backend(monkeypatch, backend)
    monkeypatch.setattr(runner, "ai_cache_enabled", lambda: False)
    runner.run_task(_TASK, "TEST")
    runner.run_task(_TASK, "TEST")
    assert len(calls) == 2
    assert not runner.cache_path(_TASK, "TEST").exists()


def test_claude_code_handoff(ai_env, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ai_backend", lambda: "claude_code")
    requests_dir = tmp_path / "requests"

    assert runner.run_task(_TASK, "test") == AiResult("pending")
    request = claude_code.request_path(_TASK, "TEST")
    assert request.name == "TEST__test_task.json"
    payload = json.loads(request.read_text())
    assert payload["ticker"] == "TEST"
    assert payload["task"] == "test_task"
    assert payload["accessions"] == ACCESSIONS
    assert payload["workspace"] == str(ai_env.resolve())
    assert payload["result_schema"] == _Answer.model_json_schema()
    response = Path(payload["response_path"])

    assert runner.run_task(_TASK, "test") == AiResult("pending")
    assert list(requests_dir.iterdir()) == [request]

    response.write_text('{"summary": 3}')
    assert runner.run_task(_TASK, "test") == AiResult("pending")
    assert request.is_file() and not response.exists()

    response.write_text('```json\n{"summary": "widgets"}\n```')
    result = runner.run_task(_TASK, "test")
    assert result == AiResult("ready", _Answer(summary="widgets"))
    assert list(requests_dir.iterdir()) == []
    assert runner.cache_path(_TASK, "test").is_file()


def test_new_filing_invalidates_cache_and_request(ai_env, monkeypatch):
    monkeypatch.setattr(runner, "ai_backend", lambda: "claude_code")
    newer = ["0000000000-25-000001", *ACCESSIONS[:1]]
    request = claude_code.request_path(_TASK, "TEST")
    response = claude_code.response_path(request)

    cache = runner.cache_path(_TASK, "TEST")
    cache.parent.mkdir(parents=True)
    old_entry = {"accessions": ACCESSIONS, "answer": {"summary": "old"}}
    cache.write_text(json.dumps(old_entry))
    assert runner.run_task(_TASK, "TEST") == AiResult("ready", _Answer(summary="old"))

    # A pending request for the old filings, answered after a new 10-K landed.
    monkeypatch.setattr(runner, "ai_cache_enabled", lambda: False)
    assert runner.run_task(_TASK, "TEST") == AiResult("pending")
    response.write_text('{"summary": "stale"}')
    monkeypatch.setattr(runner, "ai_cache_enabled", lambda: True)
    monkeypatch.setattr(runner, "latest_10ks", lambda ticker: _filings(newer))

    assert runner.run_task(_TASK, "TEST") == AiResult("pending")
    assert json.loads(request.read_text())["accessions"] == newer
    assert not response.exists()

    response.write_text('{"summary": "new"}')
    assert runner.run_task(_TASK, "TEST") == AiResult("ready", _Answer(summary="new"))
    assert json.loads(cache.read_text()) == {
        "accessions": newer,
        "answer": {"summary": "new"},
    }


@pytest.mark.parametrize("path", ["../../x", "../OTHER", "/etc/passwd"])
def test_openrouter_tools_stay_in_workspace(ai_env, path):
    with pytest.raises(ValueError, match="outside the workspace"):
        openrouter.read_file(ai_env, path)
    with pytest.raises(ValueError, match="outside the workspace"):
        openrouter.grep(ai_env, "widgets", path)
    assert "error" in openrouter._run_tool(
        ai_env, "read_file", json.dumps({"path": path})
    )


def test_openrouter_tools_read_workspace(ai_env):
    business = f"{FOLDER}/business.md"
    assert openrouter.list_files(ai_env) == f"{business} (3 lines)"
    assert openrouter.read_file(ai_env, business, offset=2) == "We sell widgets."
    assert openrouter.grep(ai_env, "WIDGET") == f"{business}:2: We sell widgets."


def test_openrouter_loop(ai_env, monkeypatch):
    replies = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "grep",
                                        "arguments": '{"pattern": "widgets"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {"message": {"role": "assistant", "content": '{"summary": "w"}'}}
                ]
            },
        ]
    )
    sent = []

    def post_chat(payload):
        sent.append(json.loads(json.dumps(payload)))
        return next(replies)

    monkeypatch.setattr(openrouter, "_post_chat", post_chat)
    assert openrouter.answer(_TASK, ai_env, "TEST", ACCESSIONS) == _Answer(summary="w")
    tool_message = sent[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["content"] == f"{FOLDER}/business.md:2: We sell widgets."
