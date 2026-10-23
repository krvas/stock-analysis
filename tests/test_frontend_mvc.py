"""Frontend MVC: only controller classes touch DOM events and dialog state.

A source-text scan, not eslint: eslint is not part of `make test`, and these
three regexes over comment-stripped source cover the rules with no config.
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "src" / "static" / "js"

LISTENER_OWNERS = frozenset(
    {
        "components/generic_input.js",
        "components/dialog_controller.js",
        "components/action_button.js",
        "components/form_controller.js",
    }
)
# The one listener outside a controller: the wizard save form's `submit`
# handler in bindWizardSaveForms, which predates FormController. Pinned to
# exactly these hits so a second handler there fails instead of riding along.
GRANDFATHERED = {"components/table_wiring.js": ['addEventListener("submit"']}
DIALOG_OWNER = "components/dialog_controller.js"

_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\w\"'])//[^\n]*", re.DOTALL)
_LISTENER = re.compile(
    r"""addEventListener\s*\(\s*(?:["'`]\w+["'`])?"""
    r"""|\.on[a-z]+\s*=(?!=)"""
    r"""|\[\s*["'`]addEventListener["'`]\s*\]"""
)
_DIALOG = re.compile(
    r"""\.showModal\s*\("""
    r"""|\[\s*["'`]showModal["'`]\s*\]"""
    r"""|\b\w*(?:dialog|drawer|modal)\w*\s*\.close\s*\(""",
    re.IGNORECASE,
)
_GLOBAL_DOM = re.compile(r"\b(?:document|window)\b")


def _code(path: Path) -> str:
    return _COMMENT.sub("", path.read_text())


def listener_hits(path: Path) -> list[str]:
    """Each place `path` attaches a DOM event handler."""
    return _LISTENER.findall(_code(path))


def dialog_hits(path: Path) -> list[str]:
    """Each place `path` opens or closes a <dialog>."""
    return _DIALOG.findall(_code(path))


def global_dom_hits(path: Path) -> list[str]:
    """Each reference to `document` or `window` in `path`'s code."""
    return _GLOBAL_DOM.findall(_code(path))


def _files() -> dict[str, Path]:
    return {p.relative_to(JS).as_posix(): p for p in JS.rglob("*.js")}


def _models() -> list[Path]:
    return sorted((JS / "components").glob("*_model.js"))


def test_only_controllers_attach_listeners() -> None:
    offenders = {
        name: hits
        for name, path in _files().items()
        if (hits := listener_hits(path))
        and name not in LISTENER_OWNERS
        and hits != GRANDFATHERED.get(name)
    }
    assert offenders == {}, (
        "listen through GenericInput, ActionButton, FormController or DialogController"
    )


def test_only_the_dialog_controller_opens_or_closes_a_dialog() -> None:
    offenders = sorted(
        name
        for name, path in _files().items()
        if dialog_hits(path) and name != DIALOG_OWNER
    )
    assert offenders == [], "open and close a <dialog> through DialogController"


def test_models_do_not_touch_the_dom() -> None:
    models = _models()
    assert {p.name for p in models} >= {"drawer_model.js", "table_model.js"}
    offenders = [p.name for p in models if global_dom_hits(p)]
    assert offenders == [], "models hold state only; controllers own the DOM"


def _sample(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "sample.js"
    path.write_text(source)
    return path


def test_listener_check_flags_every_attachment_form(tmp_path: Path) -> None:
    for bad in (
        'button.addEventListener("click", go);',
        "button.onclick = go;",
        "form.onsubmit=go;",
        'button["addEventListener"]("click", go);',
        "button.addEventListener(eventName, go);",
    ):
        assert listener_hits(_sample(tmp_path, bad)), bad
    assert not listener_hits(_sample(tmp_path, "if (a.onclick === b) {}"))


def test_grandfathered_file_fails_on_a_second_listener(tmp_path: Path) -> None:
    path = _sample(
        tmp_path,
        'form.addEventListener("submit", save);\n'
        'form.addEventListener("reset", clear);',
    )
    assert listener_hits(path) != GRANDFATHERED["components/table_wiring.js"]


def test_dialog_check_flags_open_and_close_but_not_other_close(
    tmp_path: Path,
) -> None:
    for bad in (
        "dialog.showModal();",
        'el["showModal"]();',
        "this.dialog.close();",
        "settingsDrawer.close();",
    ):
        assert dialog_hits(_sample(tmp_path, bad)), bad
    assert not dialog_hits(_sample(tmp_path, "socket.close(); stream.close();"))


def test_scans_ignore_comments(tmp_path: Path) -> None:
    path = _sample(
        tmp_path,
        "// reads window.location\n/* document.body\n dialog.showModal() */\n"
        'const url = "http://x"; // button.onclick = go\n',
    )
    assert global_dom_hits(path) == []
    assert dialog_hits(path) == []
    assert listener_hits(path) == []
    assert global_dom_hits(_sample(tmp_path, "const w = window;"))
