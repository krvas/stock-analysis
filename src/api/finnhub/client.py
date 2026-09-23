"""Finnhub stock market client — lightweight boilerplate matching other clients.

This module intentionally provides a thin wrapper around the Finnhub
HTTP API with the same structure and conventions used by the
AlphaVantage client: environment-based API key, disk cache for raw
responses, a small set of convenience parsing helpers and DataFrame
return types. It is meant as a starting point and does not implement
every endpoint or retry logic beyond BaseAPIClient's helpers.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Final

import pandas as pd
from dotenv import load_dotenv

from src.api.base_client import BaseAPIClient
from src.utils.url_cache import URLCache

logger = logging.getLogger(__name__)

BASE_URL: Final[str] = "https://finnhub.io/api/v1"
SOURCE: Final[str] = "finnhub"

FINANCIALS_FIELD_MAP: Final[dict[str, tuple[str, ...]]] = {
    "revenue": ("Revenue", "Revenues", "Net revenue", "TotalRevenue"),
    "cost_of_revenue": ("CostOfGoodsAndServicesSold", "Cost of sales", "CostOfRevenue"),
    "gross_profit": ("GrossProfit", "Gross profit"),
    "operating_expenses": ("OperatingExpenses", "Total operating expenses"),
    "operating_profit": ("OperatingIncomeLoss", "Operating income", "Operating Income"),
    "ebitda": ("EBITDA",),
    "ebit": ("EBIT",),
    "interest_expense": ("InterestExpense", "Interest expense"),
    "profit_before_tax": ("IncomeBeforeTax", "Income before tax", "Pretax income"),
    "tax_expense": ("IncomeTaxExpense", "Income tax expense"),
    "net_profit": ("NetIncomeLoss", "Net income", "Net income (loss)"),
    "eps_basic": ("BasicEarningsPerShare", "Basic EPS", "Basic earnings per share"),
    "eps_diluted": ("DilutedEarningsPerShare", "Diluted EPS", "Diluted earnings per share"),
}

BALANCE_FIELD_MAP: Final[dict[str, tuple[str, ...]]] = {
    "total_assets": ("AssetsTotal", "Total assets", "TotalAssets"),
    "current_assets": ("AssetsCurrent", "Total current assets", "CurrentAssets"),
    "non_current_assets": ("NonCurrentAssets",),
    "cash_and_equivalents": ("CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents"),
    "inventory": ("InventoryNet", "Inventories", "Inventory"),
    "receivables": ("AccountsReceivableNetCurrent", "Accounts receivable, net"),
    "total_liabilities": ("LiabilitiesTotal", "Total liabilities", "TotalLiabilities"),
    "current_liabilities": ("LiabilitiesCurrent", "Total current liabilities", "CurrentLiabilities"),
    "non_current_liabilities": ("NonCurrentLiabilities",),
    "total_debt": ("DebtTotal", "Total debt", "ShortLongTermDebtTotal"),
    "short_term_debt": ("ShortTermDebt", "Short-term debt"),
    "long_term_debt": ("LongTermDebt", "Long-term debt"),
    "total_equity": ("EquityTotal", "Total equity", "TotalShareholderEquity"),
    "retained_earnings": ("RetainedEarnings", "Retained earnings"),
}

CASH_FLOW_FIELD_MAP: Final[dict[str, tuple[str, ...]]] = {
    "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities", "Operating cash flow", "OperatingCashFlow"),
    "investing_cash_flow": ("CashFlowsFromUsedInInvestingActivities", "Investing cash flow", "InvestingCashFlow"),
    "financing_cash_flow": ("CashFlowsFromUsedInFinancingActivities", "Financing cash flow", "FinancingCashFlow"),
    "net_cash_flow": ("NetCashFlow", "Net change in cash", "NetChangeInCash"),
    "capex": ("CapitalExpenditures", "Capex"),
}

FINANCIALS_COLUMNS: Final[tuple[str, ...]] = (
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
)

BALANCE_SHEETS_COLUMNS: Final[tuple[str, ...]] = (
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
)

CASH_FLOWS_COLUMNS: Final[tuple[str, ...]] = (
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
)


class FinnhubError(Exception):
    """Raised when Finnhub returns an error payload or HTTP failure."""


class FinnhubClient(BaseAPIClient):
    """Thin wrapper around a few Finnhub endpoints.

    This is boilerplate modeled after the AlphaVantage client and is
    intentionally conservative: it provides caching, minimal validation
    and convenience methods that return pandas DataFrames.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(base_url, timeout)
        load_dotenv()
        self.api_key = api_key or os.environ.get("FINNHUB_API_KEY")
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY is required (env var or constructor argument)")
        self._cache: URLCache = URLCache(directory="data/raw/finnhub", format="json")

    def _request_error(self, message: str) -> Exception:
        return FinnhubError(message)

    def _before_request(self, path: str, params: dict[str, str]) -> None:
        safe = {k: v for k, v in params.items() if k.lower() != "token"}
        logger.info("%s GET %s params=%s", self.client_name, path, safe)

    def _validate_response(self, data: Any, path: str) -> None:
        # Finnhub typically returns JSON objects; detect common error shapes
        if isinstance(data, dict) and data.get("error"):
            raise FinnhubError(str(data.get("error")))

    def _fetch_endpoint(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
    ) -> Any:
        """GET the given API endpoint and return parsed JSON.

        `endpoint` should be a path relative to the API base (no leading
        slash required). `params` will be merged with the required token.
        """
        path = endpoint.lstrip("/")
        key = f'{path.split("/")[-1].replace("-", "_")}_{params.get("symbol", "")}'
        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        params = dict(params or {})
        params["token"] = self.api_key

        data = self._retry_wrapper(self._request, f"/{path}", params)
        self._validate_response(data, path)
        if use_cache:
            self._cache.set(key, data)
        return data

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_date(value: Any) -> object | None:
        if value is None or value == "":
            return None
        try:
            return pd.to_datetime(value).date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _match_entry(entries: list[dict[str, Any]], candidates: tuple[str, ...]) -> float | None:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            concept = str(entry.get("concept") or "")
            label = str(entry.get("label") or "")
            text = f"{concept} {label}".strip().lower()
            for candidate in candidates:
                token = str(candidate).strip().lower()
                if not token:
                    continue
                if token in text:
                    return FinnhubClient._coerce_number(entry.get("value"))
        return None

    def _iter_statement_rows(
        self,
        payload: dict[str, Any],
        *,
        section_key: str,
        field_map: dict[str, tuple[str, ...]],
        period_type: str,
        columns: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            report = item.get("report") or {}
            entries = report.get(section_key) or []
            if not isinstance(entries, list):
                continue

            row: dict[str, Any] = {
                "period_end_date": self._coerce_date(item.get("endDate")),
                "period_type": period_type,
                "fiscal_year": item.get("year"),
                "fiscal_quarter": item.get("quarter") if period_type == "quarterly" else None,
                "currency": self._infer_currency(entries),
                "source": SOURCE,
            }
            for field_name, candidates in field_map.items():
                row[field_name] = self._match_entry(entries, candidates)
            rows.append(row)

        if not rows:
            return []
        return [{column: row.get(column) for column in columns} for row in rows]

    @staticmethod
    def _infer_currency(entries: list[dict[str, Any]]) -> str:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            unit = str(entry.get("unit") or "").strip().upper()
            if unit:
                return unit
        return "USD"

    def fetch_company(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Return company profile (one-row DataFrame) for `name` (symbol)."""
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        payload = self._fetch_endpoint("stock/profile2", {"symbol": symbol}, use_cache=use_cache)

        if not payload or not payload.get("name"):
            raise FinnhubError(f"Empty profile response for symbol={symbol}")

        return pd.DataFrame([{
            "symbol": payload.get("ticker") or symbol,
            "company_name": payload.get("name") or None,
            "exchange": payload.get("exchange") or "NASDAQ",
            "country": payload.get("country") or None,
            "industry": payload.get("finnhubIndustry") or None,
            "shares_outstanding": payload.get("shareOutstanding"),
            "source": SOURCE,
        }])

    def fetch_prices(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Return a simple price snapshot as a one-row DataFrame using `/quote`.

        This is intentionally minimal — for historical OHLCV use the
        `/stock/candle` endpoint which requires `from`/`to` timestamps.
        """
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        payload = self._fetch_endpoint("quote", {"symbol": symbol}, use_cache=use_cache)

        if not isinstance(payload, dict):
            raise FinnhubError("QUOTE returned unexpected response type")

        # Finnhub quote fields: c (current), o (open), h (high), l (low), pc (prev close), t (timestamp)
        ts = payload.get("t")
        trade_time = pd.to_datetime(int(ts), unit="s") if ts else None

        return pd.DataFrame([{
            "trade_date": trade_time,
            "open": payload.get("o"),
            "high": payload.get("h"),
            "low": payload.get("l"),
            "close": payload.get("c"),
            "volume": None,
            "source": SOURCE,
        }])

    def _fetch_all_financials(self, symbol: str, use_cache: bool) -> list[tuple[dict[str, Any], str]]:
        return [
            (
                self._fetch_endpoint(
                    "stock/financials-reported",
                    {"symbol": symbol, "freq": "quarterly"},
                    use_cache=use_cache,
                ),
                "quarterly",
            ),
            (
                self._fetch_endpoint(
                    "stock/financials-reported",
                    {"symbol": symbol, "freq": "annual"},
                    use_cache=use_cache,
                ),
                "annual",
            ),
        ]

    def fetch_financials(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse income statement periods into a ``financials``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        rows: list[dict[str, Any]] = []
        for payload, period_type in self._fetch_all_financials(symbol, use_cache):
            rows.extend(
                self._iter_statement_rows(
                    payload,
                    section_key="ic",
                    field_map=FINANCIALS_FIELD_MAP,
                    period_type=period_type,
                    columns=FINANCIALS_COLUMNS,
                )
            )
        return pd.DataFrame(rows, columns=FINANCIALS_COLUMNS)

    def fetch_balance_sheets(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse balance sheet periods into a ``balance_sheets``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        rows: list[dict[str, Any]] = []
        for payload, period_type in self._fetch_all_financials(symbol, use_cache):
            rows.extend(
                self._iter_statement_rows(
                    payload,
                    section_key="bs",
                    field_map=BALANCE_FIELD_MAP,
                    period_type=period_type,
                    columns=BALANCE_SHEETS_COLUMNS,
                )
            )

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

        return pd.DataFrame(rows, columns=BALANCE_SHEETS_COLUMNS)

    def fetch_cash_flows(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Parse cash flow periods into a ``cash_flows``-shaped DataFrame."""
        use_cache = bool(kwargs.get("use_cache", True))
        symbol = name.strip().upper()
        rows: list[dict[str, Any]] = []
        for payload, period_type in self._fetch_all_financials(symbol, use_cache):
            rows.extend(
                self._iter_statement_rows(
                    payload,
                    section_key="cf",
                    field_map=CASH_FLOW_FIELD_MAP,
                    period_type=period_type,
                    columns=CASH_FLOWS_COLUMNS,
                )
            )

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
                if all(value is not None for value in parts):
                    row["net_cash_flow"] = sum(parts)  # type: ignore[arg-type]

        return pd.DataFrame(rows, columns=CASH_FLOWS_COLUMNS)

    def fetch_corporate_actions(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Boilerplate stub for corporate actions — returns empty DataFrame.

        Finnhub exposes corporate actions via specific endpoints; add
        parsing here as needed. Returning an empty DataFrame with the
        expected columns keeps callers consistent with other clients.
        """
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
