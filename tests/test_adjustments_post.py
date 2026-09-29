"""Tests for opex-to-capex POST body validation."""

from __future__ import annotations

import pytest

from src.web.routes.wizard_pages.adjustments_post import _validate_opex_to_capex_body


def _body(rows: object) -> dict[str, object]:
    return {"rows": rows}


def test_validate_opex_to_capex_body_filters_unchecked_rows() -> None:
    rows = [
        {
            "id": "us-gaap_OperatingExpenses",
            "cells": {"capitalize": True, "years": 5},
        },
        {
            "id": "us-gaap_OtherExpenses",
            "cells": {"capitalize": False, "years": None},
        },
    ]

    validated_rows, row_ids_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert validated_rows == [
        {
            "base_concept": "us-gaap_OperatingExpenses",
            "years": 5.0,
        }
    ]
    assert row_ids_to_delete == ["us-gaap_OtherExpenses"]


def test_validate_opex_to_capex_body_checked_row_missing_years_raises() -> None:
    rows = [
        {
            "id": "us-gaap_OperatingExpenses",
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
            "id": "us-gaap_OperatingExpenses",
            "cells": {"capitalize": True, "years": 5},
        },
        {
            "id": "us-gaap_ResearchAndDevelopmentExpense",
            "cells": {"capitalize": False, "years": None},
        },
    ]

    validated_rows, row_ids_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert [row["base_concept"] for row in validated_rows] == [
        "us-gaap_OperatingExpenses"
    ]
    assert row_ids_to_delete == ["us-gaap_ResearchAndDevelopmentExpense"]


def test_validate_opex_to_capex_body_unchecked_row_blank_id_skipped_from_delete() -> (
    None
):
    rows = [
        {
            "id": "",
            "cells": {"capitalize": False, "years": None},
        },
    ]

    validated_rows, row_ids_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert validated_rows == []
    assert row_ids_to_delete == []


def test_validate_opex_to_capex_body_stores_dimensional_row_id_verbatim() -> None:
    row_id = (
        "us-gaap_ResearchAndDevelopmentExpense"
        "|StatementBusinessSegmentsAxis=aapl_AmericasSegmentMember"
    )
    rows = [{"id": row_id, "cells": {"capitalize": True, "years": 4}}]

    validated_rows, row_ids_to_delete = _validate_opex_to_capex_body(_body(rows))

    assert validated_rows == [{"base_concept": row_id, "years": 4.0}]
    assert row_ids_to_delete == []
