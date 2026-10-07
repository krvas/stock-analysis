"""Triage bloat-review findings with Jev (TypeSafe).

Usage (from the repo root): ``make triage FINDINGS=<scratch>/findings-<n>.json``

Reads the reviewer's findings plus the ``intent-*.md`` notes next to them, asks
Jev one Noul question per finding ("would a careful maintainer apply this as
written?"), and writes ``triage-<n>.json`` beside the input. A finding is
``execute`` only if Jev's score is at least ``EXECUTE_THRESHOLD`` and the
reviewer did not mark it ``needs_user_decision`` (a rule kept in code, never
left to the model); everything else is ``human``. If the key is missing or the
API fails, every finding is ``human`` and ``api_status`` says why.

Not part of the app package.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from src.config import load_project_dotenv

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
EXECUTE_THRESHOLD = 0.85

_RETRY_STATUSES = {429, 529}
_MAX_ATTEMPTS = 4
_TIMEOUT_SECONDS = 60

_INSTRUCTIONS = (
    "Finding `findings.{id}` proposes a refactor of code that was just written. "
    "Would a careful maintainer of this repository apply that exact change as "
    "written, with no further discussion, given the author's `intent_notes`?"
)
_CRITERIA = {
    "true": (
        "The change removes or relocates code that is clearly redundant, dead "
        "or misplaced, matches the finding's stated fix, and contradicts "
        "nothing in the intent notes."
    ),
    "false": (
        "The change is a judgment call, contradicts or ignores an intent note, "
        "removes code declared as intentionally kept, or alters behaviour or "
        "public API."
    ),
}


class TriageError(RuntimeError):
    """The Jev call failed; the message is safe to print (never has the key)."""


def _questions(findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(finding["id"]): {
            "type": "noul",
            "instructions": _INSTRUCTIONS.format(id=finding["id"]),
            "criteria": _CRITERIA,
        }
        for finding in findings
    }


def _call_jev(
    state: dict[str, Any], questions: dict[str, Any], api_key: str
) -> dict[str, float]:
    """``{finding id: noul probability}`` from one System One request."""
    body = json.dumps({"state": state, "model": MODEL, "questions": questions})
    request = urllib.request.Request(
        API_URL,
        data=body.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
                answers = json.load(resp)["answers"]
            return {qid: float(answer["noul"]) for qid, answer in answers.items()}
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)
                continue
            raise TriageError(f"HTTP {exc.code} from {API_URL}") from exc
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            raise TriageError(f"{type(exc).__name__} calling {API_URL}") from exc
    raise TriageError("retries exhausted")  # pragma: no cover


def decide(finding: dict[str, Any], score: float | None) -> tuple[str, str]:
    """``(decision, reason)`` for one finding; the hard rules live here."""
    if finding.get("needs_user_decision"):
        return "human", "needs_user_decision"
    if score is None:
        return "human", "no score"
    if score >= EXECUTE_THRESHOLD:
        return "execute", f"score {score:.2f} >= {EXECUTE_THRESHOLD}"
    return "human", f"score {score:.2f} < {EXECUTE_THRESHOLD}"


def triage(
    findings: list[dict[str, Any]], intent_notes: str, api_key: str | None
) -> dict[str, Any]:
    """Scored and decided findings; falls back to all-``human`` on failure."""
    scores: dict[str, float] = {}
    if not api_key:
        status = "missing TYPESAFE_API_KEY: every finding goes to the human"
    elif not findings:
        status = "ok"
    else:
        state = {
            "intent_notes": intent_notes,
            "findings": {str(f["id"]): f for f in findings},
        }
        try:
            scores = _call_jev(state, _questions(findings), api_key)
            status = "ok"
        except TriageError as exc:
            status = f"error: {exc}; every finding goes to the human"

    results = []
    for finding in findings:
        score = scores.get(str(finding["id"]))
        decision, reason = decide(finding, score)
        results.append(
            {
                "id": finding["id"],
                "score": score,
                "decision": decision,
                "reason": reason,
            }
        )
    return {
        "api_status": status,
        "threshold": EXECUTE_THRESHOLD,
        "results": results,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: triage_findings.py <findings-N.json>", file=sys.stderr)
        return 2
    findings_path = Path(argv[1])
    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    intent_notes = "\n\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(findings_path.parent.glob("intent-*.md"))
    )
    load_project_dotenv()
    output = triage(findings, intent_notes, os.environ.get("TYPESAFE_API_KEY"))

    out_path = findings_path.with_name(
        findings_path.name.replace("findings", "triage", 1)
    )
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    if output["api_status"] != "ok":
        print(f"TRIAGE FALLBACK: {output['api_status']}", file=sys.stderr)
    for result in output["results"]:
        score = "n/a" if result["score"] is None else f"{result['score']:.2f}"
        print(f"{result['id']}: {result['decision']} ({score}; {result['reason']})")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
