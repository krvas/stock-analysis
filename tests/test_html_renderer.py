"""Tests for the statement-page payload and its StatementSet consumers (no network)."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from src.config import MAX_CACHE_QUARTERS, MAX_CACHE_YEARS
from src.models.edgartools.html_renderer import build_statement_payload
from src.models.statement import StatementSet
from src.web.routes.statements import clamp_num_periods
from src.web.routes.wizard_pages import adjustments_context
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


def _rows_by_id(table: dict) -> dict[str, dict]:
    return {row["id"]: row for row in table["rows"]}


def test_payload_shape_and_period_slicing() -> None:
    payload = build_statement_payload(
        _statement_set(), ticker="AAPL", period="annual", num_periods=2
    )

    assert payload["ticker"] == "AAPL"
    assert payload["period"] == "annual"
    assert set(payload["statements"]) == {"income", "balance", "cashflow"}
    for views in payload["statements"].values():
        assert set(views) == {"summary", "standard", "detailed"}
        for table in views.values():
            assert set(table) == {"columns", "linked_groups", "rows"}
            # Only the newest two periods; no row_id (or other metadata) column.
            assert [col["id"] for col in table["columns"]] == [P1, P2]
            assert all(
                col["kind"] == "static" and col["dtype"] == "number"
                for col in table["columns"]
            )


def test_payload_view_filtering_and_display_signs() -> None:
    income = build_statement_payload(
        _statement_set(), ticker="AAPL", period="annual", num_periods=3
    )["statements"]["income"]

    assert [r["id"] for r in income["summary"]["rows"]] == ["Revenue", RND]
    assert [r["id"] for r in income["standard"]["rows"]] == ["Revenue", RND]
    assert [r["id"] for r in income["detailed"]["rows"]] == [
        "Revenue",
        RND,
        "Rev|Axis=IphoneMember",
    ]

    rows = _rows_by_id(income["summary"])
    assert rows[RND]["cells"] == {P1: -5.0, P2: -4.0, P3: -3.0}
    assert rows["Revenue"]["cells"][P1] == 100.0
    assert rows[RND]["label"] == "Research and development"
    assert rows[RND]["level"] == 1


def test_clamp_num_periods() -> None:
    assert clamp_num_periods(10, "annual", 64) == min(10, MAX_CACHE_YEARS)
    assert clamp_num_periods(10_000, "annual", 10_000) == MAX_CACHE_YEARS
    assert clamp_num_periods(10_000, "quarterly", 10_000) == MAX_CACHE_QUARTERS
    assert clamp_num_periods(10, "annual", 3) == 3


def test_opex_to_capex_context_uses_detailed_projection() -> None:
    with (
        patch.object(
            adjustments_context, "load_statement_set", return_value=_statement_set()
        ) as mock_load,
        patch.object(adjustments_context, "_apply_saved_opex_to_capex_preferences"),
    ):
        context = adjustments_context.opex_to_capex_context("AAPL", "annual")

    mock_load.assert_called_once_with("AAPL", "annual")
    table = context["opex_table"]
    assert [col["id"] for col in table["columns"]] == [P1, P2, "capitalize", "years"]
    rows = table["rows"]
    # Keyed by get_row_id, not standard_concept (which only drives selection).
    assert [row["id"] for row in rows] == [RND]
    assert rows[0]["cells"] == {P1: -5.0, P2: -4.0, "capitalize": None, "years": None}


def test_opex_to_capex_prefill_matches_row_id_keys() -> None:
    prefs = pd.DataFrame(
        {
            "adjustment_type": ["opex_to_capex"] * 3,
            # The legacy standard_concept key no longer matches (exact row ids).
            "base_concept": [RND, "ResearchAndDevelopmentExpenses", "NotInTable"],
            "value": [5, 3, 2],
        }
    )
    with (
        patch.object(
            adjustments_context, "load_statement_set", return_value=_statement_set()
        ),
        patch.object(adjustments_context, "WizardDatabaseManager") as mock_db,
    ):
        db = mock_db.return_value.__enter__.return_value
        db.read_adjustment_preferences.return_value = prefs
        context = adjustments_context.opex_to_capex_context("AAPL", "annual")

    (row,) = context["opex_table"]["rows"]
    assert row["id"] == RND
    assert row["cells"]["capitalize"] is True
    assert row["cells"]["years"] == 5.0
