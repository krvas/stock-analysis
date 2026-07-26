import json
from pathlib import Path

import pandas as pd
import pytest

from src.api.finnhub.client import FinnhubClient


@pytest.fixture()
def sample_payload() -> dict:
    path = Path("data/raw/finnhub/financials_reported_AMD.json")
    with path.open() as handle:
        return json.load(handle)


def test_finnhub_statement_parsers_return_schema_aligned_dataframes(sample_payload: dict) -> None:
    client = FinnhubClient(api_key="test-key")

    def fake_fetch_endpoint(endpoint: str, params: dict | None = None, *, use_cache: bool = True):
        if endpoint != "stock/financials-reported":
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        freq = params.get("freq") if params else None
        if freq == "quarterly":
            return {"data": [sample_payload["data"][0]]}
        if freq == "annual":
            return {"data": [sample_payload["data"][1]]}
        raise AssertionError(f"Unexpected freq: {freq}")

    client._fetch_endpoint = fake_fetch_endpoint  # type: ignore[assignment]

    financials = client.fetch_financials("AMD", use_cache=False)
    balance_sheets = client.fetch_balance_sheets("AMD", use_cache=False)
    cash_flows = client.fetch_cash_flows("AMD", use_cache=False)

    assert isinstance(financials, pd.DataFrame)
    assert list(financials.columns) == [
        "period_end_date",
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "currency",
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_expenses",
        "operating_profit",
        "ebitda",
        "ebit",
        "interest_expense",
        "profit_before_tax",
        "tax_expense",
        "net_profit",
        "eps_basic",
        "eps_diluted",
        "source",
    ]
    assert financials.iloc[0]["period_type"] == "quarterly"
    assert financials.iloc[0]["revenue"] == pytest.approx(10253000000.0)

    assert isinstance(balance_sheets, pd.DataFrame)
    assert list(balance_sheets.columns) == [
        "period_end_date",
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "currency",
        "total_assets",
        "current_assets",
        "non_current_assets",
        "cash_and_equivalents",
        "inventory",
        "receivables",
        "total_liabilities",
        "current_liabilities",
        "non_current_liabilities",
        "total_debt",
        "short_term_debt",
        "long_term_debt",
        "total_equity",
        "retained_earnings",
        "source",
    ]
    assert balance_sheets.iloc[0]["cash_and_equivalents"] == pytest.approx(5585000000.0)
    assert balance_sheets.iloc[0]["non_current_assets"] == pytest.approx(28628000000 - 28628000000)

    assert isinstance(cash_flows, pd.DataFrame)
    assert list(cash_flows.columns) == [
        "period_end_date",
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "currency",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
        "capex",
        "free_cash_flow",
        "source",
    ]
    assert cash_flows.iloc[0]["operating_cash_flow"] is not None
    assert cash_flows.iloc[0]["free_cash_flow"] is not None
