"""Helpers to load API client data into the DuckDB via DatabaseManager."""

"""
TODO:
There are a few issues in this file
- A lot of ingestion is done in the API folder. It should be moved here. The API folder should only
fetch raw data.
- load_company_to_db has repeated code. It should use load_to_table to avoid repetition.
- I need to think through the architecture for ingestion. What happens if the companies table exists, but 
the financials table has just been fetched? How do we connect the company_id?
- What happens if the raw data fetched is missing a required column? We can throw an error or fill a default
- 
"""

import logging
from collections.abc import Iterable
from typing import Any

import pandas as pd

from src.api.base_client import BaseAPIClient
from src.database import tables as t
from src.database.manager import DatabaseManager

logger = logging.getLogger(__name__)


DEFAULT_TABLE_ORDER: list[str] = [
    t.COMPANIES,
    t.FINANCIALS,
    t.BALANCE_SHEETS,
    t.CASH_FLOWS,
    t.PRICES,
    t.CORPORATE_ACTIONS,
]


def load_company_to_db(
    client: BaseAPIClient,
    db: DatabaseManager,
    name: str,
    *,
    tables: Iterable[str] | None = None,
    exchange: str | None = None,
    fetch_kwargs: dict[str, Any] | None = None,
) -> None:
    """Fetch company data from client and upsert selected tables into DB.

    Args:
        client: Subclass of BaseAPIClient implementing fetch_* methods.
        db: DatabaseManager instance (open or will be opened by context).
        name: Name passed to client's fetch methods.
        tables: Iterable of table names to update. None => update all tables.
        exchange: Optional exchange string to pass/ensure for companies lookup/upsert.
        fetch_kwargs: Additional kwargs forwarded to client fetch methods.
    """
    wanted = list(tables) if tables is not None else DEFAULT_TABLE_ORDER
    fetch_kwargs = fetch_kwargs or {}

    # Ensure DB connection
    db.connect()

    # 1) Companies
    if t.COMPANIES in wanted:
        try:
            # fetch_company returns a pandas DataFrame (single-row)
            comp_df = client.fetch_company(name, **fetch_kwargs)
        except Exception:
            logger.exception("Failed to fetch company: %s", name)
            raise

        # ensure exchange present if provided
        if exchange is not None:
            # If column missing or value is null, set it
            if "exchange" not in comp_df.columns or pd.isna(comp_df.iloc[0].get("exchange", None)):
                comp_df.loc[:, "exchange"] = exchange

        db.upsert_dataframe(t.COMPANIES, comp_df)

    # Resolve company_id for downstream tables
    # Expect symbol and exchange available either from comp_df or fetch_kwargs
    symbol = None
    exch = exchange
    try:
        if 'comp_df' in locals() and 'symbol' in comp_df.columns:
            symbol = comp_df.iloc[0].get('symbol')
            exch = comp_df.iloc[0].get('exchange', exch)
    except Exception:
        pass

    company_id = None
    if symbol is not None and exch is not None:
        company_id = db.get_company_id(symbol, exch)

    # 2) Financials
    if t.FINANCIALS in wanted:
        load_to_table(client, db, t.FINANCIALS, name, company_id, fetch_kwargs)

    # 3) Balance sheets
    if t.BALANCE_SHEETS in wanted:
        load_to_table(client, db, t.BALANCE_SHEETS, name, company_id, fetch_kwargs)

    # 4) Cash flows
    if t.CASH_FLOWS in wanted:
        load_to_table(client, db, t.CASH_FLOWS, name, company_id, fetch_kwargs)

    # 5) Prices
    if t.PRICES in wanted:
        load_to_table(client, db, t.PRICES, name, company_id, fetch_kwargs)

    # 6) Corporate actions
    if t.CORPORATE_ACTIONS in wanted:
        load_to_table(client, db, t.CORPORATE_ACTIONS, name, company_id, fetch_kwargs)


def load_to_table(
        client: BaseAPIClient,
        db: DatabaseManager,
        table_name: str,
        name: str,
        company_id: str | None,
        fetch_kwargs: dict[str, Any] | None = None
    ) -> None:

    function = {
        t.COMPANIES: client.fetch_company,
        t.FINANCIALS: client.fetch_financials,
        t.BALANCE_SHEETS: client.fetch_balance_sheets,
        t.CASH_FLOWS: client.fetch_cash_flows,
        t.PRICES: client.fetch_prices,
        t.CORPORATE_ACTIONS: client.fetch_corporate_actions,
    }.get(table_name)

    if not function:
        raise ValueError(f"Unsupported table name: {table_name}")

    df = function(name, **(fetch_kwargs or {}))
    if company_id is not None and 'company_id' not in df.columns:
        df['company_id'] = company_id
    db.upsert_dataframe(table_name, df)