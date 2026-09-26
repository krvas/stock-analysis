"""Tests for opex-to-capex POST body validation."""

from __future__ import annotations

import pytest

from src.web.routes.wizard_pages.adjustments_post import _validate_opex_to_capex_body


def _body(rows: object) -> dict[str, object]:
    return {"rows": rows}


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

    validated_rows, base_concepts_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert validated_rows == [
        {
            "base_concept": "OperatingExpenses",
            "years": 5.0,
            "consolidated_ids": "a,b",
        }
    ]
    assert base_concepts_to_delete == ["OtherExpenses"]


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


def test_validate_opex_to_capex_body_unchecked_row_goes_to_delete_list() -> None:
    rows = [
        {
            "id": "OperatingExpenses",
            "cells": {"capitalize": True, "years": 5, "consolidated_ids": None},
        },
        {
            "id": "ResearchAndDevelopmentExpense",
            "cells": {"capitalize": False, "years": None},
        },
    ]

    validated_rows, base_concepts_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert [row["base_concept"] for row in validated_rows] == ["OperatingExpenses"]
    assert base_concepts_to_delete == ["ResearchAndDevelopmentExpense"]


def test_validate_opex_to_capex_body_unchecked_row_blank_id_skipped_from_delete() -> None:
    rows = [
        {
            "id": "",
            "cells": {"capitalize": False, "years": None},
        },
    ]

    validated_rows, base_concepts_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert validated_rows == []
    assert base_concepts_to_delete == []
