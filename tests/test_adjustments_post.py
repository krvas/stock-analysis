"""Tests for opex-to-capex POST body validation."""

from __future__ import annotations

import pytest

from src.web.routes.wizard_pages.adjustments_post import _validate_opex_to_capex_body


def _body(rows: object, exchange: object = "NASDAQ") -> dict[str, object]:
    return {"exchange": exchange, "rows": rows}


def test_validate_opex_to_capex_body_filters_unchecked_rows() -> None:
    rows = [
        {
            "id": "OperatingExpenses",
            "cells": {"capitalize": True, "years": 5, "consolidated_ids": "a,b"},
        },
        {
            "id": "OtherExpenses",
            "cells": {"capitalize": False, "years": None},
        },
    ]

    exchange, validated_rows = _validate_opex_to_capex_body(_body(rows))

    assert exchange == "NASDAQ"
    assert validated_rows == [
        {
            "base_concept": "OperatingExpenses",
            "years": 5.0,
            "consolidated_ids": "a,b",
        }
    ]


def test_validate_opex_to_capex_body_missing_exchange_raises() -> None:
    with pytest.raises(ValueError):
        _validate_opex_to_capex_body(_body(rows=[], exchange=""))


def test_validate_opex_to_capex_body_checked_row_missing_years_raises() -> None:
    rows = [
        {
            "id": "OperatingExpenses",
            "cells": {"capitalize": True, "years": None},
        },
    ]

    with pytest.raises(ValueError):
        _validate_opex_to_capex_body(_body(rows))


def test_validate_opex_to_capex_body_malformed_rows_not_a_list_raises() -> None:
    with pytest.raises(ValueError):
        _validate_opex_to_capex_body(_body(rows={"not": "a list"}))


def test_validate_opex_to_capex_body_malformed_rows_missing_id_raises() -> None:
    rows = [{"cells": {"capitalize": True, "years": 5}}]

    with pytest.raises(ValueError):
        _validate_opex_to_capex_body(_body(rows))
