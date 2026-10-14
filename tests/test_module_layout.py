"""Module layout: constants sit at the top of a module, right after the imports."""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
CONSTANT_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")

# (path, constant) allowed below a def or class; a None constant exempts the
# whole file. Each is built from a class it sits beside on purpose: the default
# SettingsDecl, and the AiTask built from its own result schema.
ALLOWED_BELOW_DEFINITIONS: frozenset[tuple[str, str | None]] = frozenset(
    {
        ("src/web/settings.py", "NO_SETTINGS"),
        ("src/ai_tools/tasks/one_line_answers.py", None),
    }
)


def constants_below_definitions(source: str) -> list[tuple[int, str, str]]:
    """(line, constant, first def/class) for each module-level UPPER_CASE
    assignment that comes after the module's first function or class."""
    first_definition: ast.stmt | None = None
    found: list[tuple[int, str, str]] = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first_definition = first_definition or node
            continue
        if first_definition is None:
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and CONSTANT_NAME.match(target.id):
                found.append((node.lineno, target.id, first_definition.name))
    return found


def _exemption(path: str, name: str) -> tuple[str, str | None] | None:
    for entry in ((path, name), (path, None)):
        if entry in ALLOWED_BELOW_DEFINITIONS:
            return entry
    return None


def test_constants_sit_above_every_def_and_class() -> None:
    violations: list[str] = []
    matched: set[tuple[str, str | None]] = set()
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC.parent).as_posix()
        for line, name, definition in constants_below_definitions(path.read_text()):
            exemption = _exemption(relative, name)
            if exemption is not None:
                matched.add(exemption)
                continue
            violations.append(
                f"{relative}:{line}: {name} is defined below {definition}. Move "
                f"it up to sit right after the imports. If it is built from a "
                f"class or function in this module, move that class or function "
                f"to its own module (e.g. src/web/setting_types.py beside "
                f"src/web/settings_registry.py) and import it."
            )
    violations += [
        f"ALLOWED_BELOW_DEFINITIONS entry {entry} matches no constant below a "
        f"def or class. Delete the entry from tests/test_module_layout.py."
        for entry in sorted(ALLOWED_BELOW_DEFINITIONS - matched, key=str)
    ]
    assert not violations, "\n".join(violations)


def test_flags_a_constant_below_a_class() -> None:
    source = "A = 1\n\n\nclass Decl:\n    pass\n\n\nNO_DECL = Decl()\nlogger = 1\n"
    assert constants_below_definitions(source) == [(8, "NO_DECL", "Decl")]
