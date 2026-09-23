"""Unit tests for Alpha Vantage client (no live API calls)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from src.api.alphavantage.client import AlphaVantageClient, AlphaVantageError
from src.api.alphavantage.parsing import parse_split_factor

SAMPLE_OVERVIEW = {
    "Symbol": "IBM",
    "Name": "International Business Machines",
    "Exchange": "NYSE",
    "Country": "USA",
    "Sector": "TECHNOLOGY",
    "Industry": "INFORMATION TECHNOLOGY SERVICES",
    "SharesOutstanding": "942134000",
}

SAMPLE_INCOME = {
    "symbol": "IBM",
    "annualReports": [
        {
            "fiscalDateEnding": "2024-12-31",
            "reportedCurrency": "USD",
            "totalRevenue": "62753000000",
            "costOfRevenue": "27201000000",
            "grossProfit": "35551000000",
            "operatingExpenses": "25478000000",
            "operatingIncome": "10074000000",
            "ebitda": "12176000000",
            "ebit": "7509000000",
            "interestExpense": "1712000000",
            "incomeBeforeTax": "5797000000",
            "incomeTaxExpense": "-218000000",
            "netIncome": "6023000000",
        }
    ],
    "quarterlyReports": [
        {
            "fiscalDateEnding": "2024-09-30",
            "reportedCurrency": "USD",
            "totalRevenue": "15000000000",
            "costOfRevenue": "6000000000",
            "grossProfit": "9000000000",
            "operatingExpenses": "5000000000",
            "operatingIncome": "4000000000",
            "ebitda": "4500000000",
            "ebit": "4100000000",
            "interestExpense": "400000000",
            "incomeBeforeTax": "3700000000",
            "incomeTaxExpense": "700000000",
            "netIncome": "3000000000",
        }
    ],
}

SAMPLE_EARNINGS = {
    "symbol": "IBM",
    "annualEarnings": [{"fiscalDateEnding": "2024-12-31", "reportedEPS": "6.50"}],
    "quarterlyEarnings": [{"fiscalDateEnding": "2024-09-30", "reportedEPS": "1.75"}],
}

SAMPLE_BALANCE = {
    "symbol": "IBM",
    "annualReports": [
        {
            "fiscalDateEnding": "2024-12-31",
            "reportedCurrency": "USD",
            "totalAssets": "137175000000",
            "totalCurrentAssets": "34482000000",
            "totalNonCurrentAssets": "102694000000",
            "cashAndCashEquivalentsAtCarryingValue": "13947000000",
            "inventory": "1289000000",
            "currentNetReceivables": "14010000000",
            "totalLiabilities": "109782000000",
            "totalCurrentLiabilities": "33142000000",
            "totalNonCurrentLiabilities": "76640000000",
            "shortLongTermDebtTotal": "58396000000",
            "shortTermDebt": "5857000000",
            "longTermDebt": "49884000000",
            "totalShareholderEquity": "27307000000",
            "retainedEarnings": "151163000000",
        }
    ],
    "quarterlyReports": [],
}

SAMPLE_CASH_FLOW = {
    "symbol": "IBM",
    "annualReports": [
        {
            "fiscalDateEnding": "2024-12-31",
            "reportedCurrency": "USD",
            "operatingCashflow": "13445000000",
            "cashflowFromInvestment": "-4937000000",
            "cashflowFromFinancing": "-7079000000",
            "changeInCashAndCashEquivalents": "None",
            "capitalExpenditures": "1685000000",
        }
    ],
    "quarterlyReports": [],
}

SAMPLE_PRICES = {
    "Meta Data": {"2. Symbol": "IBM"},
    "Time Series (Daily)": {
        "2024-01-03": {
            "1. open": "160.0000",
            "2. high": "162.0000",
            "3. low": "159.0000",
            "4. close": "161.0000",
            "5. adjusted close": "160.5000",
            "6. volume": "1000000",
            "7. dividend amount": "0.0000",
            "8. split coefficient": "1.0",
        },
        "2024-01-02": {
            "1. open": "158.0000",
            "2. high": "159.5000",
            "3. low": "157.0000",
            "4. close": "159.0000",
            "5. adjusted close": "158.5000",
            "6. volume": "900000",
            "7. dividend amount": "0.0000",
            "8. split coefficient": "1.0",
        },
    },
}

SAMPLE_DIVIDENDS = {
    "symbol": "IBM",
    "data": [
        {
            "ex_dividend_date": "2024-05-09",
            "declaration_date": "2024-04-30",
            "record_date": "2024-05-10",
            "payment_date": "2024-06-10",
            "amount": "1.66",
        }
    ],
}

SAMPLE_SPLITS = {
    "symbol": "IBM",
    "data": [
        {"effective_date": "1999-05-27", "split_factor": "2/1"},
    ],
}


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _dispatch(req, timeout=60):
    url = req.full_url
    if "function=OVERVIEW" in url:
        return FakeResponse(SAMPLE_OVERVIEW)
    if "function=INCOME_STATEMENT" in url:
        return FakeResponse(SAMPLE_INCOME)
    if "function=EARNINGS" in url:
        return FakeResponse(SAMPLE_EARNINGS)
    if "function=BALANCE_SHEET" in url:
        return FakeResponse(SAMPLE_BALANCE)
    if "function=CASH_FLOW" in url:
        return FakeResponse(SAMPLE_CASH_FLOW)
    if "function=TIME_SERIES_DAILY_ADJUSTED" in url:
        return FakeResponse(SAMPLE_PRICES)
    if "function=DIVIDENDS" in url:
        return FakeResponse(SAMPLE_DIVIDENDS)
    if "function=SPLITS" in url:
        return FakeResponse(SAMPLE_SPLITS)
    if "function=BAD" in url:
        return FakeResponse({"Error Message": "Invalid API call"})
    raise AssertionError(f"Unexpected URL: {url}")


class TestAlphaVantageClient:
    def test_fetch_company(self) -> None:
        client = AlphaVantageClient(api_key="test-key")
        with patch("urllib.request.urlopen", _dispatch):
            company = client.fetch_company("ibm", use_cache=False)
        assert len(company) == 1
        assert company.iloc[0]["symbol"] == "IBM"
        assert company.iloc[0]["exchange"] == "NYSE"
        assert company.iloc[0]["shares_outstanding"] == 942134000
        assert company.iloc[0]["source"] == "alphavantage"

    def test_fetch_financials_one_row_per_period(self) -> None:
        client = AlphaVantageClient(api_key="test-key")
        with patch("urllib.request.urlopen", _dispatch):
            fin = client.fetch_financials("IBM", use_cache=False)
        assert len(fin) == 2
        annual = fin[fin["period_type"] == "annual"].iloc[0]
        assert annual["revenue"] == pytest.approx(62753000000)
        assert annual["eps_diluted"] == pytest.approx(6.50)
        quarterly = fin[fin["period_type"] == "quarterly"].iloc[0]
        assert quarterly["fiscal_quarter"] == 3
        assert quarterly["eps_basic"] == pytest.approx(1.75)

    def test_fetch_balance_and_cash_flows(self) -> None:
        client = AlphaVantageClient(api_key="test-key")
        with patch("urllib.request.urlopen", _dispatch):
            bal = client.fetch_balance_sheets("IBM", use_cache=False)
            cas = client.fetch_cash_flows("IBM", use_cache=False)
        assert len(bal) == 1
        assert bal.iloc[0]["total_assets"] == pytest.approx(137175000000)
        assert len(cas) == 1
        assert cas.iloc[0]["free_cash_flow"] == pytest.approx(13445000000 - 1685000000)
        assert cas.iloc[0]["net_cash_flow"] == pytest.approx(13445000000 - 4937000000 - 7079000000)

    def test_fetch_prices(self) -> None:
        client = AlphaVantageClient(api_key="test-key")
        with patch("urllib.request.urlopen", _dispatch):
            prices = client.fetch_prices("IBM", use_cache=False, outputsize="compact")
        assert len(prices) == 2
        assert prices.iloc[0]["trade_date"] == pd.Timestamp("2024-01-02").date()
        assert prices.iloc[1]["close"] == pytest.approx(161.0)
        assert prices.iloc[1]["adj_close"] == pytest.approx(160.5)

    def test_fetch_corporate_actions(self) -> None:
        client = AlphaVantageClient(api_key="test-key")
        with patch("urllib.request.urlopen", _dispatch):
            actions = client.fetch_corporate_actions("IBM", use_cache=False)
        assert len(actions) == 2
        div = actions[actions["action_type"] == "dividend"].iloc[0]
        assert div["amount"] == pytest.approx(1.66)
        split = actions[actions["action_type"] == "split"].iloc[0]
        assert split["ratio_from"] == 1
        assert split["ratio_to"] == 2

    def test_error_payload_raises(self) -> None:
        client = AlphaVantageClient(api_key="test-key")

        def bad_urlopen(req, timeout=60):
            return FakeResponse({"Note": "API call frequency exceeded"})

        with patch("urllib.request.urlopen", bad_urlopen):
            with pytest.raises(AlphaVantageError, match="API call frequency"):
                client._fetch_function("OVERVIEW", "IBM", use_cache=False)

    def test_missing_api_key_raises(self) -> None:
        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": ""}, clear=False):
            with patch("src.api.alphavantage.client.load_dotenv"):
                with pytest.raises(ValueError, match="ALPHAVANTAGE_API_KEY"):
                    AlphaVantageClient(api_key=None)

    def test_parse_split_factor(self) -> None:
        assert parse_split_factor("4/1") == (1, 4)
        assert parse_split_factor("1/10") == (10, 1)
