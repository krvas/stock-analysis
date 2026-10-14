"""Frontend MVC: only controller classes touch DOM events and dialog state."""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "src" / "static" / "js"

LISTENER_OWNERS = frozenset(
    {
        "components/generic_input.js",
        "components/dialog_controller.js",
        "components/action_button.js",
        # The wizard save form's submit handler predates ActionButton.
        "components/table_wiring.js",
    }
)
DIALOG_OWNER = "components/dialog_controller.js"
MODELS = ("components/drawer_model.js", "components/table_model.js")


def _sources() -> dict[str, str]:
    return {p.relative_to(JS).as_posix(): p.read_text() for p in JS.rglob("*.js")}


def test_only_controllers_attach_listeners() -> None:
    offenders = sorted(
        name
        for name, source in _sources().items()
        if "addEventListener" in source and name not in LISTENER_OWNERS
    )
    assert offenders == [], (
        "listen through GenericInput, ActionButton or DialogController"
    )


def test_only_the_dialog_controller_opens_or_closes_a_dialog() -> None:
    offenders = sorted(
        name
        for name, source in _sources().items()
        if re.search(r"\.(showModal|close)\(", source) and name != DIALOG_OWNER
    )
    assert offenders == [], "open and close a <dialog> through DialogController"


def test_models_do_not_touch_the_dom() -> None:
    sources = _sources()
    offenders = [
        name for name in MODELS if re.search(r"\b(document|window)\b", sources[name])
    ]
    assert offenders == [], "models hold state only; controllers own the DOM"
