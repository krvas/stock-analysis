from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.models.statement import StatementSet
from src.web import adjusted_statements
from src.web.routes.statements import statement_context
from src.web.routes.wizard_pages import adjustments_context
from src.web.settings import Settings, resolve
from src.web.statements_registry import get_statement_page
from src.web.wizard_registry import get_subpage
from tests.statement_fixtures import make_statement

P1, P2, P3 = "2024-09-28", "2023-09-30", "2022-09-24"
RND = "us-gaap_ResearchAndDevelopmentExpense"


def _frame(statement_type: str) -> pd.DataFrame:
    raw = pd.DataFrame(
        {
            "concept": ["Revenue", RND, "Rev"],
            "label": ["Revenue", "Research and development", "iPhone"],
            "standard_concept": [
                "Revenue",
                "ResearchAndDevelopmentExpenses",
                "Revenue",
            ],
            "level": [0, 1, 1],
            "abstract": [False, False, False],
            "dimension": [False, False, True],
            "is_breakdown": [False, False, True],
            "dimension_axis": [None, None, "Axis"],
            "dimension_member": [None, None, "IphoneMember"],
            "preferred_sign": [np.nan, -1.0, np.nan],
            P1: [100.0, 5.0, 60.0],
            P2: [90.0, 4.0, 50.0],
            P3: [80.0, 3.0, 40.0],
        }
    )
    return make_statement(raw, statement_type).frame


def _statement_set() -> StatementSet:
    return StatementSet(
        income=make_statement(_frame("income"), "income"),
        balance=make_statement(_frame("balance"), "balance"),
        cashflow=make_statement(_frame("cashflow"), "cashflow"),
    )


def _opex_settings(**values: object) -> Settings:
    decl = get_subpage("adjustments", "opex-to-capex").settings
    return resolve(json.dumps(values), decl)


def _rows_by_id(table: dict) -> dict[str, dict]:
    return {row["id"]: row for row in table["rows"]}


def _statement(slug: str, specs: list | None = None, **values: object) -> dict:
    page = get_statement_page(slug)
    with (
        patch.object(
            adjusted_statements, "load_statement_set", return_value=_statement_set()
        ),
        patch.object(adjusted_statements, "load_specs", return_value=specs or []),
    ):
        return statement_context(
            "AAPL", page, resolve(json.dumps(values), page.settings)
        )


def test_statement_is_one_table_over_num_periods() -> None:
    ctx = _statement("balance", num_periods=2)
    table = ctx["statement_table"]
    assert set(table) == {
        "columns",
        "linked_groups",
        "rows",
        "calculated_cells",
        "no_input_cells",
    }
    assert [col["id"] for col in table["columns"]] == [P1, P2]
    assert all(
        col["kind"] == "static" and col["dtype"] == "number" for col in table["columns"]
    )
    assert (ctx["ticker"], ctx["period"], ctx["page"].slug) == (
        "AAPL",
        "annual",
        "balance",
    )


@pytest.mark.parametrize(
    ("view", "ids"),
    [
        ("summary", ["Revenue", RND]),
        ("standard", ["Revenue", RND]),
        ("detailed", ["Revenue", RND, "Rev|Axis=IphoneMember"]),
    ],
)
def test_statement_follows_view(view: str, ids: list[str]) -> None:
    table = _statement("income", view=view)["statement_table"]
    assert [r["id"] for r in table["rows"]] == ids


def test_statement_uses_display_signs() -> None:
    rows = _rows_by_id(_statement("income")["statement_table"])
    assert rows[RND]["cells"] == {P1: -5.0, P2: -4.0, P3: -3.0}
    assert rows["Revenue"]["cells"][P1] == 100.0
    assert rows[RND]["label"] == "Research and development"
    assert rows[RND]["level"] == 1


NO_NOTE = {"applied": [], "skipped": []}


def test_basis_decides_whether_saved_adjustments_load() -> None:
    spec = AdjustmentSpec("opex_to_capex", {"rows": {RND: 5.0}})
    reported = _statement("income", specs=[spec])
    assert (reported["basis"], reported["adjustments"]) == ("reported", NO_NOTE)
    adjusted = _statement("income", specs=[spec], basis="adjusted")
    assert adjusted["basis"] == "adjusted"
    assert adjusted["adjustments"] == {
        "applied": [{"type": "opex_to_capex", "label": "Opex capitalized (1)"}],
        "skipped": [],
    }
    no_saved = _statement("income", basis="adjusted")
    assert (no_saved["basis"], no_saved["adjustments"]) == ("adjusted", NO_NOTE)


def test_note_names_a_saved_adjustment_that_did_not_apply() -> None:
    spec = AdjustmentSpec("opex_to_capex", {"rows": {"us-gaap_Gone": 5.0}})
    note = _statement("income", specs=[spec], basis="adjusted")["adjustments"]
    assert note == {
        "applied": [],
        "skipped": [
            {
                "type": "opex_to_capex",
                "label": "Opex capitalized",
                "reason": "saved row us-gaap_Gone is not in this filing",
            }
        ],
    }


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"num_periods": 1}, [P1]),
        ({}, [P1, P2, P3]),
        ({"period": "quarterly", "num_periods": 2}, [P1, P2]),
    ],
)
def test_opex_to_capex_follows_num_periods(values: dict, expected: list) -> None:
    with (
        patch.object(
            adjusted_statements, "load_statement_set", return_value=_statement_set()
        ),
        patch.object(adjusted_statements, "load_specs", return_value=[]),
        patch.object(adjustments_context, "_apply_saved_opex_to_capex_preferences"),
    ):
        context = adjustments_context.opex_to_capex_context(
            "AAPL", _opex_settings(**values)
        )
    columns = [c["id"] for c in context["opex_table"]["columns"]]
    assert columns == [*expected, "capitalize", "years"]


def test_opex_to_capex_prefill_matches_row_id_keys() -> None:
    prefs = pd.DataFrame(
        {
            "adjustment_type": ["opex_to_capex"] * 3,
            "base_concept": [RND, "ResearchAndDevelopmentExpenses", "NotInTable"],
            "value": [5, 3, 2],
        }
    )
    with (
        patch.object(
            adjusted_statements, "load_statement_set", return_value=_statement_set()
        ),
        patch.object(adjusted_statements, "load_specs", return_value=[]),
        patch.object(adjustments_context, "WizardDatabaseManager") as mock_db,
    ):
        db = mock_db.return_value.__enter__.return_value
        db.read_adjustment_preferences.return_value = prefs
        context = adjustments_context.opex_to_capex_context("AAPL", _opex_settings())

    (row,) = context["opex_table"]["rows"]
    assert row["id"] == RND
    assert row["cells"]["capitalize"] is True
    assert row["cells"]["years"] == 5.0
