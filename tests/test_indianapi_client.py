"""Unit tests for IndianAPI client (no live API calls)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from src.api.indianapi.client import (
    IndianAPIClient,
    IndianAPIError,
    reset_request_count,
)

SAMPLE_PERIOD = {
    "EndDate": "2025-03-31",
    "FiscalYear": "2025",
    "StatementDate": "2026-03-31",
    "Type": "Annual",
    "fiscalPeriodNumber": 0,
    "stockFinancialMap": {
        "INC": [
            {"key": "TotalRevenue", "value": "54969.49", "displayName": "Revenue"},
            {"key": "NetIncome", "value": "-100.50", "displayName": "Net Income"},
            {"key": "periodType", "value": "Months", "displayName": "period Type"},
            {"key": "DilutedEPSExcludingExtraOrdItems", "value": "31.13", "displayName": "EPS"},
        ],
        "BAL": [
            {"key": "TotalAssets", "value": "1000.00", "displayName": "Assets"},
            {"key": "TotalCurrentAssets", "value": "400.00", "displayName": "CA"},
            {"key": "TotalLiabilities", "value": "600.00", "displayName": "Liab"},
            {"key": "TotalCurrentLiabilities", "value": "200.00", "displayName": "CL"},
        ],
        "CAS": [
            {"key": "CashfromOperatingActivities", "value": "500.00", "displayName": "OCF"},
            {"key": "CapitalExpenditures", "value": "-50.00", "displayName": "CapEx"},
        ],
    },
}

SAMPLE_STOCK = {
    "companyName": "Tata Steel",
    "industry": "Iron & Steel",
    "companyProfile": {
        "exchangeCodeNse": "TATASTEEL",
        "exchangeCodeBse": "500470",
        "isInId": "INE081A01020",
        "mgSector": None,
        "mgIndustry": "Iron & Steel",
    },
    "financials": [SAMPLE_PERIOD],
}


@pytest.fixture(autouse=True)
def _reset_counter() -> None:
    reset_request_count()

class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

class TestIndianAPIClient:
    def test_fetch_company_and_financials_from_mock(self) -> None:
        client = IndianAPIClient(api_key="test-key")

        def fake_urlopen(req, timeout=60):
            url = req.full_url
            payload: dict
            if "/stock?" in url:
                payload = SAMPLE_STOCK
            else:
                raise AssertionError(f"Unexpected URL: {url}")

            return FakeResponse(payload)

        with patch("urllib.request.urlopen", fake_urlopen):
            company = client.fetch_company("TATASTEEL")
            assert company["symbol"] == "TATASTEEL"
            assert company["exchange"] == "NSE"
            assert company["isin"] == "INE081A01020"
            assert company["source"] == "indianapi"

            fin = client.fetch_financials("TATASTEEL")
            assert len(fin) == 1
            assert fin.iloc[0]["revenue"] == pytest.approx(54969.49)
            assert fin.iloc[0]["net_profit"] == pytest.approx(-100.50)
            assert fin.iloc[0]["eps_diluted"] == pytest.approx(31.13)

            bal = client.fetch_balance_sheets("TATASTEEL")
            assert bal.iloc[0]["non_current_assets"] == pytest.approx(600.0)
            assert bal.iloc[0]["non_current_liabilities"] == pytest.approx(400.0)

            cas = client.fetch_cash_flows("TATASTEEL")
            assert cas.iloc[0]["free_cash_flow"] == pytest.approx(450.0)

    def test_fetch_prices_from_mock(self) -> None:
        client = IndianAPIClient(api_key="test-key")
        historical = {
            "datasets": [
                {
                    "metric": "Price",
                    "values": [["2025-06-30", "100.50"], ["2025-07-01", "101.00"]],
                },
                {
                    "metric": "Volume",
                    "values": [["2025-06-30", 1000, {"delivery": 50}], ["2025-07-01", 2000, {}]],
                },
            ]
        }

        def fake_urlopen(req, timeout=60):
            return FakeResponse(historical)

        with patch("urllib.request.urlopen", fake_urlopen):
            prices = client.fetch_prices("Reliance Industries", period="1yr")
            assert len(prices) == 2
            assert prices.iloc[1]["close"] == pytest.approx(101.0)

        with patch("urllib.request.urlopen", fake_urlopen):
            prices = client.fetch_prices("Reliance Industries", period="1yr")
            assert len(prices) == 2
            assert prices.iloc[0]["close"] == pytest.approx(100.5)
            assert prices.iloc[0]["volume"] == pytest.approx(1000)
            assert pd.isna(prices.iloc[0]["open"])

    def test_fetch_corporate_actions_from_mock(self) -> None:
        client = IndianAPIClient(api_key="test-key")
        payload = {
            "dividends": {
                "data": [
                    [
                        "05-06-2026",
                        "05-06-2026",
                        "60%",
                        "dividend of Rs.6.00 per equity share",
                    ]
                ]
            },
            "bonus": {"data": [["28-10-2024", "28-10-2024", "1:1"]]},
            "splits": {"data": []},
        }

        def fake_urlopen(req, timeout=60):
            return FakeResponse(payload)

        with patch("urllib.request.urlopen", fake_urlopen):
            actions = client.fetch_corporate_actions("Reliance Industries")
            assert len(actions) == 2
            div = actions[actions["action_type"] == "dividend"].iloc[0]
            assert div["amount"] == pytest.approx(6.0)
            bonus = actions[actions["action_type"] == "bonus"].iloc[0]
            assert bonus["ratio_from"] == 1
            assert bonus["ratio_to"] == 1

    def test_stock_error_raises(self) -> None:
        client = IndianAPIClient(api_key="test-key")

        def fake_urlopen(req, timeout=60):
            return FakeResponse({"error": "Stock not found"})

        with (
            patch("urllib.request.urlopen", fake_urlopen),
            pytest.raises(IndianAPIError, match="Stock not found"),
        ):
            client.fetch_company("Missing Co")

    def test_missing_api_key_raises(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="INDIAN_API_KEY"),
        ):
            IndianAPIClient()

