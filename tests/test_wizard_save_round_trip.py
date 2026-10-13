"""Wizard save path over HTTP, for every sub-page the registry gives a POST handler.

Each case reads the table JSON the page ships to ``table_wiring.js``, changes
every input cell the page renders an input for, posts the body
``TableModel.serialize()`` would send, and reloads the page.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.database import wizard_manager
from src.models.statement import StatementSet
from src.web import adjusted_statements
from src.web.app import app
from src.web.wizard_registry import WIZARD_PAGES
from tests.statement_fixtures import P1, P2, P3, _row, make_statement
from tests.test_assets_in_use import _balance

TICKER = "AAPL"

SAVE_PAGES = [
    pytest.param(f"/wizard/{TICKER}/{page.slug}/{sub.slug}", id=sub.slug)
    for page in WIZARD_PAGES
    for sub in page.subpages
    if sub.post_handler is not None
]
NO_SAVE_PAGES = [
    pytest.param(f"/wizard/{TICKER}/{page.slug}/{sub.slug}", id=sub.slug)
    for page in WIZARD_PAGES
    for sub in page.subpages
    if sub.post_handler is None
]

Cell = tuple[str, str]


def _statements() -> StatementSet:
    values = {P1: 10.0, P2: 9.0, P3: 8.0}
    frame = pd.DataFrame(
        [
            _row(
                "Pretax", "Pretax income", standard_concept="PretaxIncomeLoss", **values
            ),
            _row(
                "us-gaap_ResearchAndDevelopmentExpense",
                "R&D",
                standard_concept="ResearchAndDevelopmentExpenses",
                **values,
            ),
            _row(
                "us-gaap_SellingGeneralAndAdministrativeExpense",
                "SG&A",
                standard_concept="SellingGeneralAndAdminExpenses",
                **values,
            ),
            _row(
                "Dep", "Depreciation", standard_concept="DepreciationExpense", **values
            ),
            _row("us-gaap_IncreaseDecreaseInInventories", "Inventories", **values),
        ]
    )
    return StatementSet(
        income=make_statement(frame, "income"),
        balance=_balance(),
        cashflow=make_statement(frame, "cashflow"),
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_path = tmp_path / "wizard.duckdb"
    with wizard_manager.WizardDatabaseManager(db_path) as db:
        db.initialize_schema()
    monkeypatch.setattr(wizard_manager, "DEFAULT_WIZARD_DB_PATH", db_path)
    statements = _statements()
    monkeypatch.setattr(
        adjusted_statements, "load_statement_set", lambda *_: statements
    )
    yield TestClient(app)


@dataclass(frozen=True)
class SaveForm:
    action: str
    table: dict[str, Any]


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'\s{name}="([^"]*)"', tag)
    assert match, f"{name} missing on {tag}"
    return match.group(1)


def _table_json(html: str, table_id: str) -> dict[str, Any]:
    match = re.search(
        rf'<script[^>]*data-line-item-table[^>]*data-table-id="{table_id}"[^>]*>'
        r"(.*?)</script>",
        html,
        re.DOTALL,
    )
    assert match, f"no table JSON for {table_id}"
    return json.loads(match.group(1))


def _save_form(client: TestClient, url: str) -> SaveForm:
    response = client.get(url)
    assert response.status_code == 200
    forms = re.findall(r"<form[^>]*\sdata-wizard-save=[^>]*>", response.text)
    assert len(forms) == 1, f"{url} has {len(forms)} save forms"
    table_id = _attr(forms[0], "data-table-id")
    return SaveForm(_attr(forms[0], "action"), _table_json(response.text, table_id))


def _input_columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    return [col for col in table["columns"] if col["kind"] == "input"]


def _editable_cells(table: dict[str, Any]) -> list[Cell]:
    """Cells ``table_view.js`` renders an input slot for."""
    blocked = {(row_id, col_id) for row_id, col_id in table["no_input_cells"]}
    return [
        (row["id"], col["id"])
        for row in table["rows"]
        for col in _input_columns(table)
        if (row["id"], col["id"]) not in blocked
    ]


def _cells(table: dict[str, Any]) -> dict[Cell, Any]:
    return {
        (row["id"], col_id): value
        for row in table["rows"]
        for col_id, value in row["cells"].items()
    }


def _changed_value(dtype: str, current: Any, index: int) -> Any:
    if dtype == "boolean":
        return not current
    assert dtype == "number", f"no test value for dtype {dtype}"
    value = float(index + 1)
    return value if value != current else value + 0.5


def _edit(table: dict[str, Any]) -> dict[Cell, Any]:
    dtypes = {col["id"]: col["dtype"] for col in table["columns"]}
    current = _cells(table)
    return {
        cell: _changed_value(dtypes[cell[1]], current.get(cell), index)
        for index, cell in enumerate(_editable_cells(table))
    }


def _serialize(table: dict[str, Any], edits: dict[Cell, Any]) -> dict[str, Any]:
    """The body ``TableModel.serialize()`` builds after the user's edits.

    A cell absent from the shipped row is ``undefined`` in the model, and
    ``JSON.stringify`` drops it, so it stays absent here.
    """
    inputs = _input_columns(table)
    rows = []
    for row in table["rows"]:
        cells = {
            col["id"]: edits.get((row["id"], col["id"]), row["cells"][col["id"]])
            for col in inputs
            if col["id"] in row["cells"] or (row["id"], col["id"]) in edits
        }
        rows.append({"id": row["id"], "cells": cells})
    return {"columns": inputs, "rows": rows}


@pytest.mark.parametrize("url", SAVE_PAGES)
def test_saved_inputs_come_back_prefilled(client: TestClient, url: str) -> None:
    form = _save_form(client, url)
    assert form.action == url
    edits = _edit(form.table)
    assert edits, f"{url} renders no input cells to save"

    response = client.post(form.action, json=_serialize(form.table, edits))
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    reloaded = _cells(_save_form(client, url).table)
    assert {cell: reloaded.get(cell) for cell in edits} == edits


@pytest.mark.parametrize("url", SAVE_PAGES)
def test_body_that_is_not_json_is_rejected(client: TestClient, url: str) -> None:
    response = client.post(
        url, content=b"{not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Request body must be JSON"}


@pytest.mark.parametrize("url", SAVE_PAGES)
@pytest.mark.parametrize("body", [[], "rows", 3, None], ids=repr)
def test_body_that_is_not_an_object_is_rejected(
    client: TestClient, url: str, body: object
) -> None:
    response = client.post(
        url,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Request body must be a JSON object"}


def test_handler_value_error_is_a_400_naming_the_line(client: TestClient) -> None:
    url = f"/wizard/{TICKER}/adjustments/owner-earnings"
    form = _save_form(client, url)
    edits = _edit(form.table)
    row_id, col_id = next(iter(edits))
    edits[(row_id, col_id)] = 101.0

    response = client.post(url, json=_serialize(form.table, edits))

    assert response.status_code == 400
    assert response.json() == {"detail": f"{row_id} must be between 0 and 100"}
    assert _cells(_save_form(client, url).table)[(row_id, col_id)] is None


def test_opex_to_capex_bad_years_is_a_400_naming_the_line(client: TestClient) -> None:
    url = f"/wizard/{TICKER}/adjustments/opex-to-capex"
    form = _save_form(client, url)
    row_id = form.table["rows"][0]["id"]
    edits = {(row_id, "capitalize"): True, (row_id, "years"): 0.0}

    response = client.post(url, json=_serialize(form.table, edits))

    assert response.status_code == 400
    assert response.json() == {
        "detail": f"{row_id}: years must be a whole number from 1 to 100"
    }
    assert _cells(_save_form(client, url).table)[(row_id, "capitalize")] is None


@pytest.mark.parametrize("url", NO_SAVE_PAGES)
def test_sub_page_without_a_post_handler_is_404(client: TestClient, url: str) -> None:
    response = client.post(url, json={"rows": []})
    assert response.status_code == 404
    assert response.json() == {"detail": "POST not supported for this sub-page"}


def test_unknown_sub_page_is_404(client: TestClient) -> None:
    response = client.post(f"/wizard/{TICKER}/adjustments/no-such-page", json={})
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown wizard sub-page"}
