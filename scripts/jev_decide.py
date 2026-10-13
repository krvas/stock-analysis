"""Cheap pstack decisions made by Jev (TypeSafe System One).

Usage (from the repo root): ``make jev KIND=<kind> INPUT=<path.json>``; run
``scripts/jev_decide.py --help`` for each kind's input format.

Each kind in ``KINDS`` says how to read its input, what to ask Jev, and how to
turn Jev's answer into a decision. Hard rules live in each kind's ``decide``,
never in the model. ``decide(item, None)`` is the kind's fallback, used when
the key is missing, the API fails, or an item got no answer. All items of one
run go to Jev in a single request.

Writes ``<input stem>.jev.json`` beside the input and appends one JSON line
per result to ``logs/jev/decisions.jsonl``. Every constant below the imports
can be overridden by the environment variable of the same name prefixed with
``JEV_`` (``.env`` is read on import).

Not part of the app package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, load_project_dotenv

load_project_dotenv()


def _setting(name: str, default: str) -> str:
    return os.environ.get(f"JEV_{name}", default)


API_URL = _setting("API_URL", "https://api.typesafe.ai/v1/systemone")
MODEL = _setting("MODEL", "jev-latest")
MAX_ATTEMPTS = int(_setting("MAX_ATTEMPTS", "4"))
TIMEOUT_SECONDS = float(_setting("TIMEOUT_SECONDS", "60"))
# findings: execute at a score of at least 1 - margin, drop at most margin.
FINDINGS_MARGIN = float(_setting("FINDINGS_MARGIN", "0.15"))
COMMENTS_MIN_PROBABILITY = float(_setting("COMMENTS_MIN_PROBABILITY", "0.6"))
EFFORT_MIN_CONFIDENCE = float(_setting("EFFORT_MIN_CONFIDENCE", "0.5"))
ARENA_EXCLUDE = float(_setting("ARENA_EXCLUDE", "0.85"))

LOG_PATH = PROJECT_ROOT / "logs" / "jev" / "decisions.jsonl"
_RETRY_STATUSES = {429, 529}

Item = dict[str, Any]
Answer = dict[str, Any]


class JevError(RuntimeError):
    """The Jev call failed; the message is safe to print (never has the key)."""


@dataclass(frozen=True)
class Kind:
    """One decision Jev makes; see the module docstring for the contract."""

    usage: str
    items: Callable[[Any], list[Item]]
    state: Callable[[Any], dict[str, Any]]
    question: Callable[[Item], dict[str, Any]]
    decide: Callable[[Item, Answer | None], tuple[str, str]]
    load: Callable[[Path], Any] = lambda path: json.loads(
        path.read_text(encoding="utf-8")
    )
    annotate: Callable[[Item, Answer | None], dict[str, Any]] = lambda item, ans: {}
    settle: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] = lambda results: (
        results
    )


def _noul(instructions: str, yes: str, no: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": instructions,
        "criteria": {"true": yes, "false": no},
    }


def _choice(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _top(answer: Answer) -> tuple[str, float]:
    """Jev's chosen label and the probability it gave that label."""
    label = answer["choice"]
    return label, float(answer.get("probabilities", {}).get(label, 0.0))


# findings: bloat-reviewer findings -> execute / drop / human


def _load_findings(path: Path) -> dict[str, Any]:
    return {
        "findings": json.loads(path.read_text(encoding="utf-8")),
        "intent_notes": "\n\n".join(
            note.read_text(encoding="utf-8")
            for note in sorted(path.parent.glob("intent-*.md"))
        ),
    }


def _decide_finding(finding: Item, answer: Answer | None) -> tuple[str, str]:
    if finding.get("needs_user_decision"):
        return "human", "needs_user_decision"
    if answer is None:
        return "human", "no score"
    score = float(answer["noul"])
    execute, drop = 1 - FINDINGS_MARGIN, FINDINGS_MARGIN
    if score >= execute:
        return "execute", f"score {score:.2f} >= {execute:.2f}"
    if score <= drop:
        return "drop", f"score {score:.2f} <= {drop:.2f}"
    return "human", f"score {score:.2f} between {drop:.2f} and {execute:.2f}"


FINDINGS = Kind(
    usage="a bloat-reviewer findings JSON list; intent-*.md notes beside it are "
    "read too. Decides execute, drop or human.",
    load=_load_findings,
    items=lambda payload: payload["findings"],
    state=lambda payload: {
        "intent_notes": payload["intent_notes"],
        "findings": {str(f["id"]): f for f in payload["findings"]},
    },
    question=lambda finding: _noul(
        f"Finding `findings.{finding['id']}` proposes a refactor of code that was "
        "just written. Would a careful maintainer of this repository apply that "
        "exact change as written, with no further discussion, given the author's "
        "`intent_notes`?",
        yes="The change removes or relocates code that is clearly redundant, dead "
        "or misplaced, matches the finding's stated fix, and contradicts nothing "
        "in the intent notes.",
        no="The change is a judgment call, contradicts or ignores an intent "
        "note, removes code declared as intentionally kept, or alters behaviour "
        "or public API.",
    ),
    decide=_decide_finding,
)


# comments: PR review comments -> mechanical / judgment (human), fix / dismiss / ask (bot)

_HIGH_RISK = re.compile(
    r"\b(security|privacy|data[ -]loss|auth(?!or)\w*|migrat\w*)", re.IGNORECASE
)
_HUMAN_LABELS = {
    "mechanical": "The comment asks for one specific change with a single obvious "
    "implementation (a rename, a typo, a move, a check exactly as stated) that "
    "needs no design decision.",
    "judgment": "The comment raises a design, scope or product question, admits "
    "more than one reasonable answer, or the reviewer would expect discussion "
    "before an edit.",
}
_BOT_LABELS = {
    "fix": "The comment identifies a plausible correctness, security, privacy, "
    "data loss, auth, billing, migration, idempotency, race or shipped-behavior "
    "issue, or its suggested fix is small and clearly reduces risk.",
    "dismiss": "The comment matches a known low-risk noisy pattern (an intentional "
    "visual change, usage upstack the bot cannot see, temporary duplication "
    "during a parallel rewrite, a concern an existing invariant already covers, "
    "a self-withdrawn finding) and the code shown proves no change is needed.",
    "ask": "The comment is novel, high severity, touches security, privacy or "
    "data, or is ambiguous. When in doubt, ask.",
}


def _decide_comment(comment: Item, answer: Answer | None) -> tuple[str, str]:
    conservative = "ask" if comment["bot"] else "judgment"
    if answer is None:
        return conservative, "no answer"
    label, probability = _top(answer)
    if probability < COMMENTS_MIN_PROBABILITY:
        return conservative, (
            f"top label {label} at {probability:.2f} < {COMMENTS_MIN_PROBABILITY}"
        )
    if label == "dismiss" and _HIGH_RISK.search(comment["body"]):
        return "ask", "high-risk keyword in body; bot comments here are never dismissed"
    return label, f"{label} at {probability:.2f}"


COMMENTS = Kind(
    usage="a list of {id, author, bot, body, path?, line?, diff_hunk?}. Decides "
    "mechanical or judgment (human), fix, dismiss or ask (bot).",
    items=lambda comments: comments,
    state=lambda comments: {"comments": {str(c["id"]): c for c in comments}},
    question=lambda comment: _choice(
        f"Comment `comments.{comment['id']}` is a "
        + ("review-bot" if comment["bot"] else "human reviewer")
        + " comment on a pull request. How should the PR author's agent handle it?",
        _BOT_LABELS if comment["bot"] else _HUMAN_LABELS,
    ),
    decide=_decide_comment,
)


# playbook: advisory only. Jev never sees the agent's pick, so it cannot echo it.

PLAYBOOKS = {
    "investigation": "Read-only question: how does X work, why was Y built this "
    "way, are we sure about Z, should we do X or Y.",
    "bug-fix": "A reported defect to reproduce, root-cause and fix with runtime "
    "evidence.",
    "perf-issue": "A measured slowness to trace and improve against a baseline.",
    "hillclimb": "Sustained improvement of one metric against a target, looping "
    "hypotheses with before and after measurement.",
    "runtime-forensics": "Diagnose a runtime symptom (leak, idle CPU spin, glitch) "
    "from live instrumentation; the deliverable is a diagnosis.",
    "trace-forensics": "Diagnose a captured profiling artifact (cpuprofile, trace, "
    "heap snapshot); the deliverable is a diagnosis.",
    "feature": "New or changed behavior, built from a named data shape.",
    "refactoring": "A behavior-preserving change to structure or shape (rename, "
    "extract, inline, dedupe, move).",
    "prototype": "A throwaway sketch to make a design or behavioral decision "
    "cheaply, or settle an empirical fork by observing it.",
    "visual-parity": "Pixel-exact UI equivalence between two implementations or "
    "styling systems.",
    "authoring-a-skill": "Writing or editing a SKILL.md.",
    "eval": "Testing how a skill, structure or prompt change affects agent "
    "behavior before promoting it.",
    "babysit": "Driving a PR or a stack to merge-ready: conflicts, review threads, CI.",
    "shipping": "Verifying a green stack and landing it bottom-up.",
    "autonomous-run": "A long task to drive to completion without stopping.",
    "orchestrate": "A standing multi-day project with many stacked PRs and many "
    "subagents under one coordinator.",
    "autopilot-full": "A queue of independent PRs driven to merge-ready with full "
    "autonomy, one owner per PR.",
    "autopilot-stack": "A queue of changes built and verified with full autonomy, "
    "delivered as one linear stack the operator lands.",
    "session-pickup": "Resuming or taking over a prior agent's in-flight work.",
    "pause-safely": "Suspending in-flight work cleanly so it can be resumed.",
    "multi-phase-plan": "Work that spans phases or stacked PRs.",
    "worktree-cleanup": "Reclaiming disk by pruning merged or abandoned worktrees "
    "and stale simulators.",
    "opening-a-pr": "Opening a pull request for finished work.",
    "figure-it-out": "A large or cross-cutting effort, or work no other playbook fits.",
}


def _playbook_jev_choice(answer: Answer | None) -> str | None:
    return None if answer is None else answer["choice"]


def _annotate_playbook(request: Item, answer: Answer | None) -> dict[str, Any]:
    jev_choice = _playbook_jev_choice(answer)
    return {
        "agent_choice": request["agent_choice"],
        "jev_choice": jev_choice,
        "agree": jev_choice == request["agent_choice"],
        "advisory": True,
    }


def _decide_playbook(request: Item, answer: Answer | None) -> tuple[str, str]:
    jev_choice = _playbook_jev_choice(answer) or "nothing (no answer)"
    return request["agent_choice"], f"advisory only; Jev picked {jev_choice}"


PLAYBOOK = Kind(
    usage="{request, agent_choice}. Advisory: logs whether Jev agrees with "
    "agent_choice, which stays the decision.",
    items=lambda payload: [{"id": "request", **payload}],
    state=lambda payload: {"request": payload["request"]},
    question=lambda request: _choice(
        "Which poteto-mode playbook best fits the task in `request`?", PLAYBOOKS
    ),
    decide=_decide_playbook,
    annotate=_annotate_playbook,
)


# effort: reasoning effort for a delegate brief

_EFFORT_LEVELS = {
    "low": "Mechanical, fully specified edits or lookups with one obvious path.",
    "medium": "Routine changes in familiar code with a few small decisions.",
    "high": "Multi-file changes or debugging that need sustained reasoning.",
    "xhigh": "Hard design or subtle correctness work across subsystems.",
}


def _decide_effort(brief: Item, answer: Answer | None) -> tuple[str, str]:
    if answer is None:
        return "session", "no answer"
    confidence = float(answer.get("confidence", 0.0))
    if confidence < EFFORT_MIN_CONFIDENCE:
        return "session", (
            f"confidence {confidence:.2f} < {EFFORT_MIN_CONFIDENCE}; no level set"
        )
    return answer["choice"], f"confidence {confidence:.2f}"


EFFORT = Kind(
    usage="{brief}. Decides low, medium, high, xhigh or session.",
    items=lambda payload: [{"id": "brief", **payload}],
    state=lambda payload: {"brief": payload["brief"]},
    question=lambda brief: _choice(
        "A subagent will carry out the delegate brief in `brief`. Pick the "
        "cheapest reasoning effort level at which it would still do the job "
        "correctly. Prefer the lower level whenever it would suffice.",
        _EFFORT_LEVELS,
    ),
    decide=_decide_effort,
)


# arena: flag only obviously broken candidates; never rank or pick a base


def _decide_candidate(candidate: Item, answer: Answer | None) -> tuple[str, str]:
    if answer is None:
        return "keep", "no score"
    score = float(answer["noul"])
    if score >= ARENA_EXCLUDE:
        return "exclude", f"obviously broken at {score:.2f} >= {ARENA_EXCLUDE}"
    return "keep", f"broken score {score:.2f} < {ARENA_EXCLUDE}"


def _keep_at_least_one(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results or any(r["decision"] == "keep" for r in results):
        return results
    return [
        {
            **r,
            "decision": "keep",
            "reason": f"every candidate scored broken; keeping all ({r['reason']})",
        }
        for r in results
    ]


ARENA = Kind(
    usage="a list of {id, report} from arena runners. Decides exclude or keep.",
    items=lambda candidates: candidates,
    state=lambda candidates: {"candidates": {str(c["id"]): c for c in candidates}},
    question=lambda candidate: _noul(
        f"Candidate `candidates.{candidate['id']}` is one runner's attempt at a "
        "shared task, described by its own report. Is it obviously broken?",
        yes="The report shows it fails to build, its tests fail, or it did not "
        "do the task.",
        no="It builds, its tests pass, and it attempted the task, whatever its "
        "quality relative to other candidates.",
    ),
    decide=_decide_candidate,
    settle=_keep_at_least_one,
)


KINDS: dict[str, Kind] = {
    "findings": FINDINGS,
    "comments": COMMENTS,
    "playbook": PLAYBOOK,
    "effort": EFFORT,
    "arena": ARENA,
}


def _check_answer(question: dict[str, Any], answer: Any) -> None:
    if question["type"] == "noul":
        float(answer["noul"])
    elif answer["choice"] not in question["criteria"]:
        raise ValueError("choice outside criteria")


def _call_jev(
    state: dict[str, Any], questions: dict[str, Any], api_key: str
) -> dict[str, Answer]:
    """``{question id: raw answer}`` from one System One request."""
    body = json.dumps({"state": state, "model": MODEL, "questions": questions})
    request = urllib.request.Request(
        API_URL,
        data=body.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:
                answers = json.load(resp)["answers"]
            for qid, answer in answers.items():
                _check_answer(questions[qid], answer)
            return answers
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)
                continue
            raise JevError(f"HTTP {exc.code} from {API_URL}") from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise JevError(f"{type(exc).__name__} calling {API_URL}") from exc
    raise JevError("retries exhausted")  # pragma: no cover


def _log(kind_name: str, results: list[dict[str, Any]]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as log:
        for result in results:
            log.write(
                json.dumps({"timestamp": timestamp, "kind": kind_name, **result}) + "\n"
            )


def run(kind_name: str, payload: Any, api_key: str | None) -> dict[str, Any]:
    """Decided items for one kind; falls back per kind when Jev is unavailable."""
    kind = KINDS[kind_name]
    items = kind.items(payload)
    answers: dict[str, Answer] = {}
    if not api_key:
        status = "missing TYPESAFE_API_KEY: fallback decisions"
    elif not items:
        status = "ok"
    else:
        questions = {str(item["id"]): kind.question(item) for item in items}
        try:
            answers = _call_jev(kind.state(payload), questions, api_key)
            status = "ok"
        except JevError as exc:
            status = f"error: {exc}; fallback decisions"

    results = []
    for item in items:
        answer = answers.get(str(item["id"]))
        decision, reason = kind.decide(item, answer)
        results.append(
            {
                "id": item["id"],
                "answer": answer,
                "decision": decision,
                "reason": reason,
                **kind.annotate(item, answer),
            }
        )
    results = kind.settle(results)
    _log(kind_name, results)
    return {"kind": kind_name, "api_status": status, "results": results}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="jev_decide.py",
        description="Ask Jev for one kind of pstack decision.",
        epilog="kinds and their input:\n"
        + "\n".join(f"  {name}: {kind.usage}" for name, kind in KINDS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("input", type=Path, help="path to the input JSON")
    args = parser.parse_args(argv[1:])
    kind_name, input_path = args.kind, args.input
    payload = KINDS[kind_name].load(input_path)
    output = run(kind_name, payload, os.environ.get("TYPESAFE_API_KEY"))

    out_path = input_path.with_name(f"{input_path.stem}.jev.json")
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    if output["api_status"] != "ok":
        print(f"JEV FALLBACK: {output['api_status']}", file=sys.stderr)
    for result in output["results"]:
        print(f"{result['id']}: {result['decision']} ({result['reason']})")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
