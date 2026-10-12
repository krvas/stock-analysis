from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import src.web.routes  # noqa: F401
from src.adjustments.registry import ADJUSTMENT_TYPES
from src.web.wizard_registry import WIZARD_PAGES

REPO = Path(__file__).resolve().parents[1]
COMPONENTS = "src/static/js/components"
WIZARD_PAGES_DIR = "src/web/routes/wizard_pages"

SHARED_FILES_HEADING = "## Before adding code to a shared/generic file"
SHARED_PATH_BULLET = re.compile(r"- `([^`\s]+)`")


def parse_shared_files(claude_md: str) -> tuple[str, ...]:
    _, found, section = claude_md.partition(f"\n{SHARED_FILES_HEADING}\n")
    if not found:
        raise ValueError(f"CLAUDE.md has no {SHARED_FILES_HEADING!r} section")
    section = section.split("\n## ", 1)[0]
    lines = section.splitlines()
    first = next((i for i, line in enumerate(lines) if line.startswith("- ")), None)
    if first is None:
        raise ValueError(f"{SHARED_FILES_HEADING!r} has no bulleted shared-file list")
    paths = []
    for line in lines[first:]:
        if not line.strip():
            break
        bullet = SHARED_PATH_BULLET.fullmatch(line)
        if bullet is None:
            raise ValueError(
                f"CLAUDE.md shared-file list line {line!r} is not one backticked path"
            )
        paths.append(bullet.group(1))
    return tuple(paths)


SHARED_FILES = parse_shared_files((REPO / "CLAUDE.md").read_text())

IDENTITY_REGISTRY = "src/web/wizard_registry.py"

SUBPAGE_HOME = (
    f"{WIZARD_PAGES_DIR}/<name>.py (context builder or POST handler) or "
    "src/templates/wizard/<page>/<subpage>.html (markup)"
)


def _column_ids(source: str) -> set[str]:
    ids: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ColumnSpec"
        ):
            continue
        args = [kw.value for kw in node.keywords if kw.arg == "id"] + node.args[:1]
        ids.update(
            a.value
            for a in args
            if isinstance(a, ast.Constant) and type(a.value) is str
        )
    return ids


def _is_compound_name(token: str) -> bool:
    return "-" in token or "_" in token


def subpage_token_origins() -> dict[str, str]:
    found: dict[str, str] = {}
    for page in WIZARD_PAGES:
        for sub in page.subpages:
            found[sub.slug] = f"sub-page slug in {IDENTITY_REGISTRY}"
    for type_id in ADJUSTMENT_TYPES:
        found[type_id] = "adjustment type id in src/adjustments/registry.py"
    for path in sorted((REPO / WIZARD_PAGES_DIR).glob("*.py")):
        for col_id in _column_ids(path.read_text()):
            found[col_id] = f"column id in {path.relative_to(REPO)}"
    return {token: src for token, src in found.items() if _is_compound_name(token)}


@dataclass(frozen=True)
class Rule:
    name: str
    paths: tuple[str, ...]
    pattern: re.Pattern[str]
    home: str
    origins: dict[str, str] = field(default_factory=dict)


def _token_rule() -> Rule:
    origins = subpage_token_origins()
    tokens = sorted(origins, key=len, reverse=True)
    return Rule(
        name="shared files name no sub-page (CLAUDE.md: Before adding code to a "
        "shared/generic file)",
        paths=tuple(p for p in SHARED_FILES if p != IDENTITY_REGISTRY),
        pattern=re.compile(
            r"(?<![\w-])(" + "|".join(map(re.escape, tokens)) + r")(?![\w-])"
        ),
        home=SUBPAGE_HOME,
        origins=origins,
    )


TOKEN_RULE = _token_rule()


def _components_except(*keep: str) -> tuple[str, ...]:
    return tuple(
        str(p.relative_to(REPO))
        for p in sorted((REPO / COMPONENTS).glob("*.js"))
        if p.name not in keep
    )


EDIT_EVENTS = "input|change|beforeinput|keydown|keyup|keypress|paste"

MVC_RULES: tuple[Rule, ...] = (
    Rule(
        name="only generic_input.js creates table-input event handlers; other "
        "components listen only to a literal non-edit event such as "
        '"submit" (CLAUDE.md: Frontend table MVC)',
        paths=_components_except("generic_input.js"),
        pattern=re.compile(
            rf"""addEventListener\((?!\s*(["'`])(?!({EDIT_EVENTS})\1)[a-z]+\1)"""
            rf"|\.on({EDIT_EVENTS})\s*=(?!=)"
        ),
        home=f"{COMPONENTS}/generic_input.js; subscribe to the GenericInput",
    ),
    Rule(
        name="table_wiring.js and table_view.js do not read or write input "
        "element state (CLAUDE.md: Frontend table MVC)",
        paths=(f"{COMPONENTS}/table_wiring.js", f"{COMPONENTS}/table_view.js"),
        pattern=re.compile(r"\.(value|checked)\b"),
        home=f"GenericInput in {COMPONENTS}/generic_input.js; save from "
        "model.serialize()",
    ),
    Rule(
        name="table_view.js only paints and attaches no listeners "
        "(CLAUDE.md: Frontend table MVC)",
        paths=(f"{COMPONENTS}/table_view.js",),
        pattern=re.compile(r"addEventListener\(|\.on[a-z]+\s*=(?!=)"),
        home=f"{COMPONENTS}/generic_input.js (inputs) or "
        f"{COMPONENTS}/table_wiring.js (forms)",
    ),
)


def _describe(rule: Rule, matched: str) -> str:
    origin = rule.origins.get(matched)
    return f"{matched!r} ({origin})" if origin else repr(matched)


def violations(rule: Rule, path: str, text: str) -> list[str]:
    return [
        f"{path}:{line_no}: {_describe(rule, match.group(0))} breaks rule: "
        f"{rule.name}. Put this code in {rule.home}."
        for line_no, line in enumerate(text.splitlines(), start=1)
        for match in rule.pattern.finditer(line)
    ]


def test_shared_files_exist() -> None:
    missing = [p for p in SHARED_FILES if not (REPO / p).is_file()]
    assert not missing, f"CLAUDE.md lists shared files that do not exist: {missing}"


@pytest.mark.parametrize(
    "doc",
    [
        "# Rules\n\n- `src/models/table.py`\n",
        f"\n{SHARED_FILES_HEADING}\n\nShared files: none listed.\n",
        f"\n{SHARED_FILES_HEADING}\n\n- `src/models/table.py`\n- see the test\n",
    ],
    ids=["no heading", "no bullets", "bullet that is not a path"],
)
def test_shared_file_list_rejects_unparseable_section(doc: str) -> None:
    with pytest.raises(ValueError):
        parse_shared_files(doc)


def test_every_registry_contributes_tokens() -> None:
    sources = " ".join(subpage_token_origins().values())
    for source in ("sub-page slug", "adjustment type id", "column id"):
        assert source in sources, f"no {source} derived; the derivation broke"


@pytest.mark.parametrize(
    "rule", [TOKEN_RULE, *MVC_RULES], ids=lambda r: r.name.split(" (")[0]
)
def test_rule_holds(rule: Rule) -> None:
    found = [
        v
        for path in rule.paths
        for v in violations(rule, path, (REPO / path).read_text())
    ]
    assert not found, "\n".join(found)


PAST_MISTAKES = [
    pytest.param(
        TOKEN_RULE,
        f"{COMPONENTS}/table_wiring.js",
        'const SAVE_FIELDS = {\n  "opex-to-capex": { capitalize: "capitalize", '
        'years: "years" },\n};',
        id="slug-keyed save-field dict",
    ),
    pytest.param(
        MVC_RULES[0],
        f"{COMPONENTS}/table_view.js",
        'element.addEventListener("change", handleChange);',
        id="input listener in table_view",
    ),
    pytest.param(
        MVC_RULES[0],
        f"{COMPONENTS}/table_wiring.js",
        "input.addEventListener(evt, handleChange);",
        id="listener with a variable event name",
    ),
    pytest.param(
        MVC_RULES[1],
        f"{COMPONENTS}/table_wiring.js",
        'input.value = value == null ? "" : value;',
        id="input state written by table_wiring",
    ),
    pytest.param(
        MVC_RULES[1],
        f"{COMPONENTS}/table_view.js",
        "coerced = element.checked;",
        id="input state read by table_view",
    ),
    pytest.param(
        MVC_RULES[2],
        f"{COMPONENTS}/table_view.js",
        'element.addEventListener("input", handleChange);',
        id="listener in table_view",
    ),
]


@pytest.mark.parametrize(("rule", "path", "snippet"), PAST_MISTAKES)
def test_rule_catches_past_mistake(rule: Rule, path: str, snippet: str) -> None:
    assert path in rule.paths
    assert violations(rule, path, snippet)
