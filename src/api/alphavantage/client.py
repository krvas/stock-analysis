"""Alpha Vantage stock market client — fetch and parse only (no retries, no DB writes)."""

from __future__ import annotations

import logging
import os
from typing import Any, Final

import pandas as pd
from dotenv import load_dotenv

from src.api.alphavantage.parsing import (
    DEFAULT_CURRENCY,
    SOURCE,
    parse_date,
    parse_int,
    parse_number,
    parse_split_factor,
    period_metadata,
)
from src.api.base_client import BaseAPIClient
from src.utils.url_cache import URLCache

logger = logging.getLogger(__name__)

BASE_URL: Final[str] = "https://www.alphavantage.co"

# Schema column <- Alpha Vantage report field(s)
INCOME_FIELD_MAP: Final[dict[str, str]] = {
    "revenue": "totalRevenue",
    "cost_of_revenue": "costOfRevenue",
    "gross_profit": "grossProfit",
    "operating_expenses": "operatingExpenses",
    "operating_profit": "operatingIncome",
    "ebitda": "ebitda",
    "ebit": "ebit",
    "interest_expense": "interestExpense",
    "profit_before_tax": "incomeBeforeTax",
    "tax_expense": "incomeTaxExpense",
    "net_profit": "netIncome",
    "eps_basic": "basicEPS",
    "eps_diluted": "dilutedEPS",
}

BALANCE_FIELD_MAP: Final[dict[str, str]] = {
    "total_assets": "totalAssets",
    "current_assets": "totalCurrentAssets",
    "non_current_assets": "totalNonCurrentAssets",
    "cash_and_equivalents": "cashAndCashEquivalentsAtCarryingValue",
    "inventory": "inventory",
    "receivables": "currentNetReceivables",
    "total_liabilities": "totalLiabilities",
    "current_liabilities": "totalCurrentLiabilities",
    "non_current_liabilities": "totalNonCurrentLiabilities",
    "total_debt": "shortLongTermDebtTotal",
    "short_term_debt": "shortTermDebt",
    "long_term_debt": "longTermDebt",
    "total_equity": "totalShareholderEquity",
    "retained_earnings": "retainedEarnings",
}

CASH_FLOW_FIELD_MAP: Final[dict[str, str]] = {
    "operating_cash_flow": "operatingCashflow",
    "investing_cash_flow": "cashflowFromInvestment",
    "financing_cash_flow": "cashflowFromFinancing",
    "net_cash_flow": "changeInCashAndCashEquivalents",
    "capex": "capitalExpenditures",
}


class AlphaVantageError(Exception):
    """Raised when Alpha Vantage returns an error payload or HTTP failure."""


class AlphaVantageClient(BaseAPIClient):
    """Thin wrapper around Alpha Vantage fundamental and time-series endpoints.

    Endpoints used (see https://www.alphavantage.co/documentation/):
    - OVERVIEW — company metadata
    - INCOME_STATEMENT / BALANCE_SHEET / CASH_FLOW — statements (annual + quarterly)
    - EARNINGS — EPS by period (merged into financials when statement lacks EPS)
    - TIME_SERIES_DAILY — daily OHLCV + close
    - DIVIDENDS / SPLITS — corporate actions
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(base_url, timeout)
        load_dotenv()
        self.api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError("ALPHAVANTAGE_API_KEY is required (env var or constructor argument)")
        self._cache: URLCache = URLCache(directory="data/raw/alphavantage", format="json")

    def _request_error(self, message: str) -> Exception:
        return AlphaVantageError(message)

    def _before_request(self, path: str, params: dict[str, str]) -> None:
        safe = {k: v for k, v in params.items() if k != "apikey"}
        logger.info("%s GET %s params=%s", self.client_name, path, safe)

    def _validate_response(self, data: Any, path: str) -> None:
        if not isinstance(data, dict):
            return
        for key in ("Error Message", "Note", "Information"):
            message = data.get(key)
            if message:
                raise AlphaVantageError(f"{key}: {message}")

    def _fetch_function(
        self,
        function: str,
        symbol: str,
        *,
        extra_params: dict[str, str] | None = None,
        use_cache: bool = True,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        """GET ``/query`` for ``function`` + ``symbol``, with optional disk cache."""
        resolved = symbol.strip().upper()
        key = cache_key or f"{function.lower()}_{resolved}"
        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        params: dict[str, str] = {
            "function": function,
            "symbol": resolved,
            "apikey": self.api_key,
        }
        if extra_params:
            params.update(extra_params)

        data = self._retry_wrapper(self._request, "/query", params)
        if not isinstance(data, dict):
            raise AlphaVantageError(
                f"Unexpected {function} response type: {type(data).__name__}"
            )
        if use_cache:
            self._cache.set(key, data)
        return data

    @staticmethod
    def _map_report_fields(
        report: dict[str, Any],
        field_map: dict[str, str],
    ) -> dict[str, float | None]:
        return {
            column: parse_number(report.get(av_key))
            for column, av_key in field_map.items()
        }

    def _iter_statement_rows(
        self,
        payload: dict[str, Any],
        field_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for period_type, section in (
            ("annual", "annualReports"),
            ("quarterly", "quarterlyReports"),
        ):
            for report in payload.get(section) or []:
                if not isinstance(report, dict):
                    continue
                try:
                    meta = period_metadata(report, period_type)
                except ValueError:
                    continue
                row = {**meta, **self._map_report_fields(report, field_map)}
                row["source"] = SOURCE
                rows.append(row)
        return rows

    def _eps_by_date(self, symbol: str, *, use_cache: bool = True) -> dict[str, float | None]:
        payload = self._fetch_function("EARNINGS", symbol, use_cache=use_cache)
        eps: dict[str, float | None] = {}
        for section in ("annualEarnings", "quarterlyEarnings"):
            for item in payload.get(section) or []:
                if not isinstance(item, dict):
                    continue
                ending = item.get("fiscalDateEnding")
                if ending:
                    eps[str(ending)] = parse_number(item.get("reportedEPS"))
        return eps

    def fetch_company(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Return one-row DataFrame aligned with ``companies`` schema (minus ``company_id``)."""
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        payload = self._fetch_function("OVERVIEW", symbol, use_cache=use_cache)

        if not payload or not payload.get("Symbol"):
            raise AlphaVantageError(f"Empty OVERVIEW response for symbol={symbol}")

        return pd.DataFrame([{
            "symbol": str(payload.get("Symbol") or symbol),
            "exchange": payload.get("Exchange"),
            "country": payload.get("Country"),
            "isin": None,
            "company_name": payload.get("Name") or symbol,
            "sector": payload.get("Sector"),
            "industry": payload.get("Industry"),
            "shares_outstanding": parse_int(payload.get("SharesOutstanding")),
            "shares_diluted": None,
            "listing_date": None,
            "is_active": True,
            "source": SOURCE,
        }])

    def fetch_financials(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse income statement periods into a ``financials``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        payload = self._fetch_function("INCOME_STATEMENT", symbol, use_cache=use_cache)

        rows = self._iter_statement_rows(payload, INCOME_FIELD_MAP)
        return pd.DataFrame(rows)

    def fetch_balance_sheets(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse balance sheet periods into a ``balance_sheets``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        payload = self._fetch_function(
            "BALANCE_SHEET", name.strip().upper(), use_cache=use_cache
        )
        rows = self._iter_statement_rows(payload, BALANCE_FIELD_MAP)
        for row in rows:
            total_assets = row.get("total_assets")
            current_assets = row.get("current_assets")
            if row.get("non_current_assets") is None and total_assets is not None and current_assets is not None:
                row["non_current_assets"] = total_assets - current_assets

            total_liabilities = row.get("total_liabilities")
            current_liabilities = row.get("current_liabilities")
            if (
                row.get("non_current_liabilities") is None
                and total_liabilities is not None
                and current_liabilities is not None
            ):
                row["non_current_liabilities"] = total_liabilities - current_liabilities
        return pd.DataFrame(rows)

    def fetch_cash_flows(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse cash flow periods into a ``cash_flows``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        payload = self._fetch_function(
            "CASH_FLOW", name.strip().upper(), use_cache=use_cache
        )
        rows = self._iter_statement_rows(payload, CASH_FLOW_FIELD_MAP)
        for row in rows:
            ocf = row.get("operating_cash_flow")
            capex = row.get("capex")
            if ocf is not None and capex is not None:
                row["free_cash_flow"] = ocf - abs(capex)
            else:
                row["free_cash_flow"] = None

            if row.get("net_cash_flow") is None:
                parts = [
                    row.get("operating_cash_flow"),
                    row.get("investing_cash_flow"),
                    row.get("financing_cash_flow"),
                ]
                if all(p is not None for p in parts):
                    row["net_cash_flow"] = sum(parts)  # type: ignore[arg-type]
        return pd.DataFrame(rows)

    def fetch_prices(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Return daily OHLCV rows aligned with ``prices`` schema (minus ``company_id``)."""
        use_cache = bool(kwargs.get("use_cache", True))
        outputsize = str(kwargs.get("outputsize", "compact"))
        symbol = name.strip().upper()
        cache_key = f"time_series_daily_{symbol}_{outputsize}"
        payload = self._fetch_function(
            "TIME_SERIES_DAILY",
            symbol,
            extra_params={"outputsize": outputsize},
            use_cache=use_cache,
            cache_key=cache_key,
        )

        series = payload.get("Time Series (Daily)") or {}
        if not isinstance(series, dict):
            raise AlphaVantageError("TIME_SERIES_DAILY missing Time Series (Daily)")

        rows: list[dict[str, Any]] = []
        for trade_date_str, bar in series.items():
            if not isinstance(bar, dict):
                continue
            trade_date = parse_date(trade_date_str)
            if trade_date is None:
                continue
            close = parse_number(bar.get("4. close"))
            if close is None:
                continue
            rows.append({
                "trade_date": trade_date,
                "open": parse_number(bar.get("1. open")),
                "high": parse_number(bar.get("2. high")),
                "low": parse_number(bar.get("3. low")),
                "close": close,
                "volume": parse_int(bar.get("5. volume")),
                "source": SOURCE,
            })

        if not rows:
            return pd.DataFrame(
                columns=["trade_date", "open", "high", "low", "close", "volume", "adj_close", "source"]
            )
        return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)

    def fetch_corporate_actions(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse dividends and splits into a ``corporate_actions``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        currency = str(kwargs.get("currency", DEFAULT_CURRENCY))
        symbol = name.strip().upper()

        dividends_payload = self._fetch_function("DIVIDENDS", symbol, use_cache=use_cache)
        splits_payload = self._fetch_function("SPLITS", symbol, use_cache=use_cache)

        rows: list[dict[str, Any]] = []

        for item in dividends_payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            action_date = parse_date(item.get("ex_dividend_date"))
            if action_date is None:
                continue
            rows.append({
                "action_date": action_date,
                "action_type": "dividend",
                "ex_date": action_date,
                "record_date": parse_date(item.get("record_date")),
                "payment_date": parse_date(item.get("payment_date")),
                "currency": currency,
                "amount": parse_number(item.get("amount")),
                "ratio_from": None,
                "ratio_to": None,
                "description": None,
                "source": SOURCE,
            })

        for item in splits_payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            action_date = parse_date(item.get("effective_date"))
            if action_date is None:
                continue
            ratio_from, ratio_to = parse_split_factor(item.get("split_factor"))
            rows.append({
                "action_date": action_date,
                "action_type": "split",
                "ex_date": action_date,
                "record_date": None,
                "payment_date": None,
                "currency": currency,
                "amount": None,
                "ratio_from": ratio_from,
                "ratio_to": ratio_to,
                "description": str(item.get("split_factor")) if item.get("split_factor") else None,
                "source": SOURCE,
            })

        if not rows:
            return pd.DataFrame(
                columns=[
                    "action_date",
                    "action_type",
                    "ex_date",
                    "record_date",
                    "payment_date",
                    "currency",
                    "amount",
                    "ratio_from",
                    "ratio_to",
                    "description",
                    "source",
                ]
            )
        return pd.DataFrame(rows).sort_values(["action_date", "action_type"]).reset_index(drop=True)
