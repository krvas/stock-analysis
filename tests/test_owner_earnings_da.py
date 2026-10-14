from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.adjustments.engine import apply_adjustments
from src.adjustments.types import owner_earnings as oe
from src.api.edgartools.standard_terms import CFO, DA_COMPONENT_AXIS
from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import StatementSet
from src.web import adjusted_statements
from src.web.routes.wizard_pages import owner_earnings as page
from src.web.settings import resolve
from src.web.wizard_registry import get_subpage
from tests.js_fixtures import check_calculated_cells_fixture
from tests.statement_fixtures import P1, P2, P3, _row, make_statement

PRETAX = "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
DA = "us-gaap_DepreciationDepletionAndAmortization"
OLD_DA = "us-gaap_DepreciationAmortizationAndAccretionNet"
FULL_BREAKDOWN, NO_BREAKDOWN, OLD_LINE_PARTIAL = P1, P2, P3


def _component(member: str, **values: float) -> dict:
    return _row(
        DA,
        member,
        standard_concept="DepreciationExpense",
        dimension=True,
        is_breakdown=True,
        dimension_axis=DA_COMPONENT_AXIS,
        dimension_member=member,
        parent_concept=CFO,
        **values,
    )


def aapl_shape() -> StatementSet:
    income = pd.DataFrame(
        [
            _row(
                PRETAX,
                "Pretax income",
                standard_concept="PretaxIncomeLoss",
                **{FULL_BREAKDOWN: 100.0, NO_BREAKDOWN: 80.0, OLD_LINE_PARTIAL: 60.0},
            )
        ]
    )
    da = {"standard_concept": "DepreciationExpense", "parent_concept": CFO}
    cashflow = pd.DataFrame(
        [
            _row(
                DA,
                "Depreciation and amortization",
                **da,
                **{FULL_BREAKDOWN: 30.0, NO_BREAKDOWN: 25.0},
            ),
            _component("us-gaap_Depreciation", **{FULL_BREAKDOWN: 20.0}),
            _component(
                "us-gaap_AmortizationOfIntangibleAssets",
                **{FULL_BREAKDOWN: 10.0, OLD_LINE_PARTIAL: 4.0},
            ),
            _row(
                OLD_DA,
                "Depreciation, amortization and accretion",
                **da,
                **{OLD_LINE_PARTIAL: 18.0},
            ),
            _row(
                CFO,
                "Cash from operations",
                **{FULL_BREAKDOWN: 130.0, NO_BREAKDOWN: 105.0, OLD_LINE_PARTIAL: 78.0},
            ),
        ]
    )
    return StatementSet(
        income=make_statement(income, "income"),
        balance=make_statement(income.iloc[0:0], "balance"),
        cashflow=make_statement(cashflow, "cashflow"),
    )


def _cashflow_set(rows: list[dict]) -> StatementSet:
    income = pd.DataFrame(
        [_row(PRETAX, "Pretax income", standard_concept="PretaxIncomeLoss")]
    )
    return StatementSet(
        income=make_statement(income, "income"),
        balance=make_statement(income.iloc[0:0], "balance"),
        cashflow=make_statement(pd.DataFrame(rows), "cashflow"),
    )


def _items(ss: StatementSet) -> dict[str, tuple[str, list[float | None]]]:
    items = oe.da_items(ss.cashflow)
    return {
        r["row_id"]: (
            r["label"],
            [None if np.isnan(r[p]) else r[p] for p in (P1, P2, P3)],
        )
        for r in items.to_dict(orient="records")
    }


def test_da_matches_the_da_line_in_every_period() -> None:
    da = oe.components(aapl_shape())["da"]
    assert da.to_dict() == pytest.approx({P1: 30.0, P2: 25.0, P3: 18.0})


def test_line_slot_holds_only_the_periods_the_components_do_not_explain() -> None:
    assert _items(aapl_shape()) == {
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_Depreciation": (
            "us-gaap_Depreciation",
            [20.0, None, None],
        ),
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_AmortizationOfIntangibleAssets": (
            "us-gaap_AmortizationOfIntangibleAssets",
            [10.0, None, None],
        ),
        DA: (
            "Depreciation and amortization (years without a note breakdown)",
            [None, 25.0, 18.0],
        ),
    }


def test_extension_line_summed_into_continuing_operations_cfo_is_the_line() -> None:
    extension = "mu_DepreciationandAmortizationofIntangibleAssets"
    ss = _cashflow_set(
        [
            _row("mu_DepreciationSupplemental", "Not in CFO", **{P2: 99.0}),
            _row(
                extension,
                "D&A",
                parent_concept=f"{CFO}ContinuingOperations",
                **{P2: 10.0, P3: 8.0},
            ),
            _component("us-gaap_Depreciation", **{P2: 6.0, P3: 7.0}),
            _component("us-gaap_AmortizationOfIntangibleAssets", **{P2: 4.0}),
        ]
    )
    assert _items(ss) == {
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_Depreciation": (
            "us-gaap_Depreciation",
            [None, 6.0, None],
        ),
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_AmortizationOfIntangibleAssets": (
            "us-gaap_AmortizationOfIntangibleAssets",
            [None, 4.0, None],
        ),
        extension: ("D&A (years without a note breakdown)", [None, None, 8.0]),
    }


def test_components_pass_through_when_there_is_no_line() -> None:
    ss = _cashflow_set(
        [
            _component("us-gaap_Depreciation", **{P1: 20.0, P2: 15.0}),
            _component("us-gaap_AmortizationOfIntangibleAssets", **{P1: 10.0}),
        ]
    )
    assert _items(ss) == {
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_Depreciation": (
            "us-gaap_Depreciation",
            [20.0, 15.0, None],
        ),
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_AmortizationOfIntangibleAssets": (
            "us-gaap_AmortizationOfIntangibleAssets",
            [10.0, None, None],
        ),
    }


@pytest.mark.parametrize(
    ("line", "parts", "expected"),
    [
        (None, {}, {}),
        (None, {"dep": 1.0}, {"dep": 1.0}),
        (("line", 10.0), {"dep": 6.0, "amort": 4.0}, {"dep": 6.0, "amort": 4.0}),
        (("line", 10.0), {"dep": 6.0, "amort": 4.5}, {"dep": 6.0, "amort": 4.5}),
        (("line", 10.0), {"dep": 6.0, "amort": 3.4}, {"line": 10.0}),
        (("line", 10.0), {"amort": 4.0}, {"line": 10.0}),
        (("line", 10.0), {}, {"line": 10.0}),
    ],
)
def test_parts_or_line(
    line: tuple[str, float] | None, parts: dict[str, float], expected: dict
) -> None:
    assert oe._parts_or_line(line, parts) == expected


@pytest.fixture
def aapl_shape_wizard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "wizard.duckdb"
    monkeypatch.setattr("src.database.wizard_manager.DEFAULT_WIZARD_DB_PATH", path)
    monkeypatch.setattr(
        adjusted_statements, "load_statement_set", lambda *_: aapl_shape()
    )
    with WizardDatabaseManager(path) as db:
        db.initialize_schema()


def test_page_matches_engine_on_aapl_shape(aapl_shape_wizard: None) -> None:
    pcts = {
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_Depreciation": 60.0,
        f"{DA}|{DA_COMPONENT_AXIS}=us-gaap_AmortizationOfIntangibleAssets": 20.0,
        DA: 40.0,
        page.NWC_ROW: 50.0,
    }
    page.owner_earnings_post(
        "AAPL",
        {
            "rows": [
                {"id": row, "cells": {page.PCT_COLUMN.id: pct}}
                for row, pct in pcts.items()
            ]
        },
    )
    decl = get_subpage("adjustments", "owner-earnings").settings
    table = page.owner_earnings_context("AAPL", resolve(json.dumps({}), decl))[
        "oe_table"
    ]
    run = apply_adjustments(aapl_shape(), adjusted_statements.load_specs("AAPL"))
    memo = run.statements.cashflow.frame.set_index("row_id")
    expected = {
        (page.OE_ROW, p): float(memo.at["adj_OwnerEarnings", p]) for p in (P1, P2, P3)
    }
    assert expected == pytest.approx(
        {
            (page.OE_ROW, P1): 100 + 30 - (0.6 * 20 + 0.2 * 10),
            (page.OE_ROW, P2): 80 + 25 - 0.4 * 25,
            (page.OE_ROW, P3): 60 + 18 - 0.4 * 18,
        }
    )
    check_calculated_cells_fixture(
        "owner_earnings_aapl_shape_table.json", table, expected
    )
