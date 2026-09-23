"""Tests for wizard adjustment_preferences storage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.database import read_adjustment_preferences, upsert_adjustment_preferences
from src.database import wizard_tables as wt
from src.database.wizard_manager import WizardDatabaseManager


@pytest.fixture
def wizard_db_path(tmp_path: Path) -> Path:
    return tmp_path / "wizard.duckdb"


@pytest.fixture
def wizard_db(wizard_db_path: Path) -> WizardDatabaseManager:
    with WizardDatabaseManager(wizard_db_path) as manager:
        manager.initialize_schema()
        yield manager


def _sample_row(**overrides: object) -> dict[str, object]:
    row = {
        "ticker": "AAPL",
        "exchange": "NASDAQ",
        "statement": "PL",
        "adjustment_type": "opex_to_capex",
        "base_concept": "ResearchAndDevelopmentExpense",
        "base_concept_statement": "PL",
        "value": 3.0,
        "consolidated_ids": "c1,c2",
    }
    row.update(overrides)
    return row


def test_initialize_wizard_schema_creates_table(wizard_db: WizardDatabaseManager) -> None:
    assert wizard_db.list_tables() == [wt.ADJUSTMENT_PREFERENCES]


def test_upsert_and_read_adjustment_preferences(wizard_db_path: Path) -> None:
    df = pd.DataFrame([_sample_row()])
    result = upsert_adjustment_preferences(df, db_path=wizard_db_path)
    assert result.rows_written == 1

    loaded = read_adjustment_preferences("aapl", "nasdaq", db_path=wizard_db_path)
    assert len(loaded) == 1
    assert loaded.iloc[0]["ticker"] == "AAPL"
    assert loaded.iloc[0]["value"] == 3.0


def test_upsert_updates_on_unique_key(wizard_db_path: Path) -> None:
    upsert_adjustment_preferences(
        pd.DataFrame([_sample_row(value=2.0)]),
        db_path=wizard_db_path,
    )
    upsert_adjustment_preferences(
        pd.DataFrame([_sample_row(value=5.0)]),
        db_path=wizard_db_path,
    )

    loaded = read_adjustment_preferences("AAPL", "NASDAQ", db_path=wizard_db_path)
    assert len(loaded) == 1
    assert loaded.iloc[0]["value"] == 5.0
    assert loaded.iloc[0]["adjustment_id"] == "0"


def test_upsert_ignores_external_adjustment_id(wizard_db_path: Path) -> None:
    upsert_adjustment_preferences(
        pd.DataFrame([_sample_row(adjustment_id="999")]),
        db_path=wizard_db_path,
    )
    loaded = read_adjustment_preferences("AAPL", "NASDAQ", db_path=wizard_db_path)
    assert loaded.iloc[0]["adjustment_id"] == "0"


def test_sequential_adjustment_ids(wizard_db_path: Path) -> None:
    upsert_adjustment_preferences(
        pd.DataFrame(
            [
                _sample_row(base_concept="ResearchAndDevelopmentExpense"),
                _sample_row(base_concept="SellingGeneralAndAdministrative"),
            ]
        ),
        db_path=wizard_db_path,
    )
    loaded = read_adjustment_preferences("AAPL", "NASDAQ", db_path=wizard_db_path)
    ids = sorted(loaded["adjustment_id"].tolist())
    assert ids == ["0", "1"]


def test_delete_adjustment_preferences_removes_only_matching_row(
    wizard_db: WizardDatabaseManager,
) -> None:
    df = pd.DataFrame(
        [
            _sample_row(base_concept="ResearchAndDevelopmentExpense"),
            _sample_row(base_concept="SellingGeneralAndAdministrative"),
            _sample_row(base_concept="OtherOperatingExpense"),
        ]
    )
    wizard_db.upsert_adjustment_preferences(df)

    result = wizard_db.delete_adjustment_preferences(
        [("AAPL", "NASDAQ", "opex_to_capex", "SellingGeneralAndAdministrative")]
    )
    assert result.rows_deleted == 1

    loaded = wizard_db.read_adjustment_preferences("AAPL", "NASDAQ")
    remaining = sorted(loaded["base_concept"].tolist())
    assert remaining == ["OtherOperatingExpense", "ResearchAndDevelopmentExpense"]


def test_delete_adjustment_preferences_nonexistent_key_is_noop(
    wizard_db: WizardDatabaseManager,
) -> None:
    wizard_db.upsert_adjustment_preferences(pd.DataFrame([_sample_row()]))

    result = wizard_db.delete_adjustment_preferences(
        [("AAPL", "NASDAQ", "opex_to_capex", "DoesNotExist")]
    )
    assert result.rows_deleted == 0

    loaded = wizard_db.read_adjustment_preferences("AAPL", "NASDAQ")
    assert len(loaded) == 1


def test_delete_adjustment_preferences_empty_keys_is_noop(
    wizard_db: WizardDatabaseManager,
) -> None:
    wizard_db.upsert_adjustment_preferences(pd.DataFrame([_sample_row()]))

    result = wizard_db.delete_adjustment_preferences([])
    assert result.rows_deleted == 0

    loaded = wizard_db.read_adjustment_preferences("AAPL", "NASDAQ")
    assert len(loaded) == 1


def test_delete_adjustment_preferences_matches_case_insensitively(
    wizard_db: WizardDatabaseManager,
) -> None:
    wizard_db.upsert_adjustment_preferences(
        pd.DataFrame([_sample_row(ticker="aapl", exchange="nasdaq")])
    )

    result = wizard_db.delete_adjustment_preferences(
        [("aapl", "nasdaq", "opex_to_capex", "ResearchAndDevelopmentExpense")]
    )
    assert result.rows_deleted == 1

    loaded = wizard_db.read_adjustment_preferences("AAPL", "NASDAQ")
    assert len(loaded) == 0
