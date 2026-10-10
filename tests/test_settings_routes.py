from __future__ import annotations

import json
import re
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from src.web import adjusted_statements
from src.web.app import app
from tests.test_statement_pages import P1, P2, P3, _statement_set

FUND_FLOW = "/wizard/AAPL/business-understanding/fund-flow"
BALANCE_SHEET_SIZE = "/wizard/AAPL/business-understanding/balance-sheet-size"
OFFSET_ERROR = "Previous period must be older than the current period"
ADJUSTED_NOTE = "Adjusted basis (no adjustments applied)"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with (
        patch.object(
            adjusted_statements, "load_statement_set", return_value=_statement_set()
        ),
        patch.object(adjusted_statements, "load_specs", return_value=[]),
    ):
        yield TestClient(app)


def _save(client: TestClient, **form: str) -> Response:
    return client.post("/settings", data=form, follow_redirects=False)


def _table(html: str, table_id: str = "statement-table") -> dict:
    match = re.search(rf'id="{table_id}-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match, f"{table_id} JSON missing"
    return json.loads(match.group(1))


def _columns(html: str, table_id: str = "statement-table") -> list[str]:
    return [c["id"] for c in _table(html, table_id)["columns"]]


def test_bare_statements_url_redirects_to_income(client: TestClient) -> None:
    response = client.get("/statements/aapl", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/statements/AAPL/income"


def test_unknown_statement_is_404(client: TestClient) -> None:
    assert client.get("/statements/AAPL/bogus").status_code == 404


@pytest.mark.parametrize(
    ("next_path", "location"),
    [
        ("/statements/AAPL/balance", "/statements/AAPL/balance"),
        ("//evil.com", "/"),
        ("https://x", "/"),
    ],
)
def test_save_redirects_only_to_a_local_next(
    client: TestClient, next_path: str, location: str
) -> None:
    response = _save(client, view="detailed", next=next_path)
    assert response.status_code == 303
    assert response.headers["location"] == location


def test_saved_cookie_is_httponly_lax_root_for_a_year(client: TestClient) -> None:
    header = _save(client, view="detailed", next="/").headers["set-cookie"]
    name, *attrs = (part.strip().lower() for part in header.split(";"))
    assert name.startswith("settings=")
    assert {
        "httponly",
        "samesite=lax",
        "path=/",
        "max-age=31536000",
    } <= set(attrs)


def test_saved_settings_shape_the_next_statement_page(client: TestClient) -> None:
    before = client.get("/statements/AAPL/income").text
    assert _columns(before) == [P1, P2, P3]
    assert ADJUSTED_NOTE not in before

    _save(client, num_periods="2", basis="adjusted", next="/statements/AAPL/balance")

    after = client.get("/statements/AAPL/income").text
    assert _columns(after) == [P1, P2]
    assert ADJUSTED_NOTE in after


def test_saved_offsets_shape_the_next_fund_flow(client: TestClient) -> None:
    assert _columns(client.get(FUND_FLOW).text, "fund-flow-table") == [
        P1,
        P2,
        "change",
    ]
    _save(client, current_period="1", previous_period="2", next=FUND_FLOW)
    assert _columns(client.get(FUND_FLOW).text, "fund-flow-table") == [
        P2,
        P3,
        "change",
    ]


def test_view_post_applies(client: TestClient) -> None:
    standard = _table(client.get("/statements/AAPL/income").text)["rows"]
    _save(client, view="detailed", next="/statements/AAPL/income")
    detailed = _table(client.get("/statements/AAPL/income").text)["rows"]
    assert len(detailed) > len(standard)


def test_refused_save_keeps_settings_and_reports_once(client: TestClient) -> None:
    _save(client, num_periods="2", next="/")
    stored = client.cookies.get("settings")

    response = _save(client, current_period="2", previous_period="1", next=FUND_FLOW)
    assert response.status_code == 303
    assert response.headers["location"] == FUND_FLOW
    set_cookies = response.headers.get_list("set-cookie")
    assert not any(c.startswith("settings=") for c in set_cookies)
    assert client.cookies.get("settings") == stored

    first = client.get(FUND_FLOW).text
    assert OFFSET_ERROR in first
    assert "data-open-on-load" in first

    second = client.get(FUND_FLOW).text
    assert OFFSET_ERROR not in second
    assert "data-open-on-load" not in second


def test_query_params_do_not_override_settings(client: TestClient) -> None:
    plain = _table(client.get("/statements/AAPL/income").text)
    queried = client.get(
        "/statements/AAPL/income?period=quarterly&num_periods=1&basis=adjusted"
    ).text
    assert _table(queried) == plain
    assert ADJUSTED_NOTE not in queried


def test_landing_drawer_has_global_settings_only(client: TestClient) -> None:
    html = client.get("/wizard/AAPL").text
    assert "Global" in html
    assert "This page" not in html


def test_statement_drawer_offers_basis_for_this_page(client: TestClient) -> None:
    html = client.get("/statements/AAPL/income").text
    assert html.index("This page") < html.index('name="basis"')
    assert "settings-reason" not in html


@pytest.mark.parametrize(
    ("url", "reasons"),
    [
        (BALANCE_SHEET_SIZE, ("Annual only", "Single period", "Summary only")),
        (FUND_FLOW, ("Two periods",)),
    ],
)
def test_greyed_global_settings_show_their_reason(
    client: TestClient, url: str, reasons: tuple[str, ...]
) -> None:
    html = client.get(url).text
    for reason in reasons:
        assert re.search(rf'class="settings-reason"[^>]*>{reason}<', html)
