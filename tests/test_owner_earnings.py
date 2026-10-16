"""Owner Earnings sub-page: tables, saving maintenance %, and parity with the
engine. Saves go to a real temporary wizard DuckDB."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.adjustments.engine import apply_adjustments
from src.adjustments.types import owner_earnings as oe
from src.database.wizard_manager import WizardDatabaseManager
from src.web import adjusted_statements
from src.web.routes.wizard_pages import owner_earnings as page
from src.web.settings import resolve
from src.web.wizard_registry import get_subpage
from tests.js_fixtures import check_calculated_cells_fixture
from tests.owner_earnings_fixture import (
    AMORTIZATION,
    DEPRECIATION,
    OWNER_EARNINGS,
    SAVED,
    filing,
)
from tests.statement_fixtures import P1, P2, P3


@pytest.fixture(autouse=True)
def wizard_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "wizard.duckdb"
    monkeypatch.setattr("src.database.wizard_manager.DEFAULT_WIZARD_DB_PATH", path)
    monkeypatch.setattr(adjusted_statements, "load_statement_set", lambda *_: filing())
    with WizardDatabaseManager(path) as db:
        db.initialize_schema()
    return path


def _saved(path: Path) -> dict[str, tuple[float, str, str, str]]:
    with WizardDatabaseManager(path, read_only=True) as db:
        prefs = db.read_adjustment_preferences("AAPL", "NASDAQ")
    return {
        r.base_concept: (
            r.value,
            r.adjustment_type,
            r.statement,
            r.base_concept_statement,
        )
        for r in prefs.itertuples()
    }


def _context(**values: object) -> dict:
    decl = get_subpage("adjustments", "owner-earnings").settings
    return page.owner_earnings_context("AAPL", resolve(json.dumps(values), decl))


def _row(row_id: str, pct: object) -> dict:
    return {"id": row_id, "cells": {page.PCT_COLUMN.id: pct}}


def _post(*rows: dict) -> dict:
    return page.owner_earnings_post("AAPL", {"rows": list(rows)})


def _post_saved() -> dict:
    return _post(
        _row(page.PRETAX_ROW, None),
        _row(DEPRECIATION, SAVED[DEPRECIATION]),
        _row(AMORTIZATION, str(SAVED[AMORTIZATION])),
        _row(page.NWC_ROW, SAVED[oe.MAINTENANCE_NWC]),
        _row(page.OE_ROW, None),
    )


def _period_columns(table: dict) -> list[str]:
    return [c["id"] for c in table["columns"] if c["kind"] == "static"]


@pytest.mark.parametrize(
    ("num_periods", "expected"), [(1, [P1]), (2, [P1, P2]), (10, [P1, P2, P3])]
)
def test_tables_follow_num_periods(num_periods: int, expected: list[str]) -> None:
    ctx = _context(num_periods=num_periods)
    assert _period_columns(ctx["oe_table"]) == expected
    assert _period_columns(ctx["nwc_table"]) == expected


def test_post_saves_each_pct_under_its_row_and_nwc_under_maintenance_nwc(
    wizard_db: Path,
) -> None:
    assert _post_saved() == {"ok": True, "rows_written": 3}
    assert _saved(wizard_db) == {
        DEPRECIATION: (60.0, oe.TYPE_ID, "CF", "CF"),
        AMORTIZATION: (20.0, oe.TYPE_ID, "CF", "CF"),
        oe.MAINTENANCE_NWC: (50.0, oe.TYPE_ID, "CF", "CF"),
    }


@pytest.mark.parametrize("blank", [None, ""])
def test_post_saves_a_blank_pct_as_zero(wizard_db: Path, blank: object) -> None:
    _post(_row(DEPRECIATION, blank), _row(page.NWC_ROW, blank))
    assert {k: v[0] for k, v in _saved(wizard_db).items()} == {
        DEPRECIATION: 0.0,
        oe.MAINTENANCE_NWC: 0.0,
    }


@pytest.mark.parametrize("pct", [0, 100])
def test_post_accepts_the_bounds(wizard_db: Path, pct: float) -> None:
    _post(_row(DEPRECIATION, pct))
    assert _saved(wizard_db)[DEPRECIATION][0] == pct


@pytest.mark.parametrize(
    ("row_id", "named"),
    [(DEPRECIATION, DEPRECIATION), (page.NWC_ROW, oe.MAINTENANCE_NWC)],
)
@pytest.mark.parametrize(
    ("pct", "problem"),
    [(-0.5, "between 0 and 100"), (100.5, "between 0 and 100"), ("abc", "a number")],
)
def test_post_rejects_a_bad_pct_naming_the_line_and_writes_nothing(
    wizard_db: Path, row_id: str, named: str, pct: object, problem: str
) -> None:
    with pytest.raises(ValueError) as err:
        _post(_row(AMORTIZATION, 10), _row(row_id, pct))
    assert str(err.value) == f"{named} must be {problem}"
    assert _saved(wizard_db) == {}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({}, "rows is required"),
        ({"rows": []}, "rows is required"),
        (
            {"rows": [_row(page.PRETAX_ROW, 5), _row(page.OE_ROW, 5), _row("", 5)]},
            "no maintenance % rows in body",
        ),
    ],
)
def test_post_without_maintenance_rows_is_rejected(
    wizard_db: Path, body: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        page.owner_earnings_post("AAPL", body)
    assert _saved(wizard_db) == {}


def test_saved_pcts_come_back_in_the_page_table() -> None:
    _post_saved()
    rows = {row["id"]: row["cells"] for row in _context()["oe_table"]["rows"]}
    assert {r: rows[r][page.PCT_COLUMN.id] for r in rows} == {
        page.PRETAX_ROW: None,
        DEPRECIATION: 60.0,
        AMORTIZATION: 20.0,
        page.NWC_ROW: 50.0,
        page.OE_ROW: None,
    }


def test_js_owner_earnings_fixture_matches_the_page_and_engine_after_a_save() -> None:
    _post_saved()
    table = _context()["oe_table"]
    run = apply_adjustments(filing(), adjusted_statements.load_specs("AAPL"))
    memo = run.statements.cashflow.frame.set_index("row_id")
    expected = {
        (page.OE_ROW, period): float(memo.at["adj_OwnerEarnings", period])
        for period in _period_columns(table)
    }
    assert expected == pytest.approx(
        {(page.OE_ROW, period): value for period, value in OWNER_EARNINGS.items()}
    )
    check_calculated_cells_fixture("owner_earnings_table.json", table, expected)
