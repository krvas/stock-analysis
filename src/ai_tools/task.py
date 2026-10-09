"""Task and result types shared by the runner and the backends."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

AiStatus = Literal["ready", "pending"]


@dataclass(frozen=True)
class AiTask[T: BaseModel]:
    """A question answered from a 10-K workspace as JSON shaped like ``result_model``.

    Define one per module under ``src/ai_tools/tasks/`` as a module constant.
    ``name`` keys the cache and the OpenRouter model choice.
    """

    name: str
    instructions: str
    result_model: type[T]

    def result_schema(self) -> str:
        """The answer's JSON schema, as text for the agent."""
        return json.dumps(self.result_model.model_json_schema(), indent=2)

    def parse(self, text: str) -> T:
        """Validate a JSON answer (```` ```json ```` fences allowed).

        Raises ``pydantic.ValidationError`` when it does not match the model.
        """
        body = text.strip()
        if body.startswith("```"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
            body = body.rsplit("```", 1)[0]
        return self.result_model.model_validate_json(body)


@dataclass(frozen=True)
class AiResult[T: BaseModel]:
    """``ready`` with the validated ``answer``, or ``pending`` (no answer yet)."""

    status: AiStatus
    answer: T | None = None
