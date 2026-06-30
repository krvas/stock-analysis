"""Tests for DatabaseManager."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.database.manager import DatabaseManager
from src.database import tables as t


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.duckdb"


@pytest.fixture
def db(db_path: Path) -> DatabaseManager:
    with DatabaseManager(db_path) as manager:
        manager.initialize_schema()
        yield manager


def test_initialize_schema_creates_tables(db: DatabaseManager) -> None:
    assert set(db.list_tables()) == set(t.ALL_TABLES)


def test_upsert_companies_assigns_ids(db: DatabaseManager) -> None:
    df = pd.DataFrame(
        [
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "company_name": "Reliance Industries Ltd",
            }
        ]
    )
    result = db.upsert_dataframe(t.COMPANIES, df)
    assert result.rows_written == 1

    company_id = db.get_company_id("RELIANCE", "NSE")
    assert company_id == 1
    assert db.table_row_count(t.COMPANIES) == 1


def test_upsert_companies_no_duplicate(db: DatabaseManager) -> None:
    row = {"symbol": "TCS", "exchange": "NSE", "company_name": "Tata Consultancy Services"}
    db.upsert_dataframe(t.COMPANIES, pd.DataFrame([row]))
    db.upsert_dataframe(t.COMPANIES, pd.DataFrame([{**row, "sector": "IT"}]))
    assert db.table_row_count(t.COMPANIES) == 1

    updated = db.query("SELECT sector FROM companies WHERE symbol = 'TCS'")
    assert updated.iloc[0]["sector"] == "IT"


def test_upsert_prices(db: DatabaseManager) -> None:
    db.upsert_dataframe(
        t.COMPANIES,
        pd.DataFrame([{"symbol": "INFY", "exchange": "NSE", "company_name": "Infosys Ltd"}])
    )
    company_id = db.get_company_id("INFY", "NSE")
    assert company_id is not None

    prices = pd.DataFrame(
        [
            {
                "company_id": company_id,
                "trade_date": "2024-01-01",
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "volume": 1_000_000,
            },
            {
                "company_id": company_id,
                "trade_date": "2024-01-02",
                "open": 104.0,
                "high": 106.0,
                "low": 103.0,
                "close": 105.5,
                "volume": 900_000,
            },
        ]
    )
    db.upsert_dataframe(t.PRICES, prices)
    assert db.table_row_count(t.PRICES) == 2

    # Re-upsert same key with new close — still 2 rows
    prices.iloc[0, prices.columns.get_loc("close")] = 101.0
    db.upsert_dataframe(t.PRICES, prices.iloc[[0]])
    assert db.table_row_count(t.PRICES) == 2
    close = db.query(
        "SELECT close FROM prices WHERE company_id = ? AND trade_date = ?",
        [company_id, "2024-01-01"],
    ).iloc[0]["close"]
    assert close == 101.0


def test_max_trade_date(db: DatabaseManager) -> None:
    db.upsert_dataframe(
        t.COMPANIES,
        pd.DataFrame([{"symbol": "HDFCBANK", "exchange": "NSE", "company_name": "HDFC Bank"}])
    )
    cid = db.get_company_id("HDFCBANK", "NSE")
    db.upsert_dataframe(
        t.PRICES,
        pd.DataFrame(
            [{"company_id": cid, "trade_date": "2023-06-01", "close": 1500.0}]
        )
    )
    assert db.max_trade_date(cid) == pd.Timestamp("2023-06-01")


def test_context_manager_closes(db_path: Path) -> None:
    with DatabaseManager(db_path) as db:
        db.initialize_schema()
    # Second open should work after close
    with DatabaseManager(db_path) as db:
        assert len(db.list_tables()) == len(t.ALL_TABLES)

def test_load_parquet(db: DatabaseManager) -> None:
    db.load_parquet(t.COMPANIES, "tests/data/companies.parquet")
    assert db.table_row_count(t.COMPANIES) == 1
    assert db.query("SELECT company_name FROM companies WHERE symbol = 'RELIANCE'").iloc[0]["company_name"] == "Reliance Industries Ltd"
