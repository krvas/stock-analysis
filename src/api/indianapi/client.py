"""IndianAPI.in stock market client — fetch and parse only (no retries, no DB writes)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Final
from dotenv import load_dotenv

import pandas as pd

from src.api.base_client import BaseAPIClient
from src.utils.indianapi_parsing import (
    DEFAULT_CURRENCY,
    coalesce,
    map_fields,
    parse_action_date,
    parse_dividend_amount,
    parse_ratio,
    period_metadata,
    rows_to_dict,
)
from src.utils.url_cache import URLCache
from .registry_manager import RegistryManager

logger = logging.getLogger(__name__)

BASE_URL: Final[str] = "https://stock.indianapi.in"
SOURCE: Final[str] = "indianapi"


_request_count: int = 0


def get_request_count() -> int:
    """Return cumulative API requests made in this process."""
    return _request_count


def reset_request_count() -> None:
    """Reset the module-level request counter (intended for tests)."""
    global _request_count
    _request_count = 0


class IndianAPIError(Exception):
    """Raised when the Indian API returns an error payload or HTTP failure."""


def resolve_api_name(registry_manager: RegistryManager, symbol_or_name: str, company_name_hint: str | None = None) -> str:
    """Map NSE symbol or ambiguous name to a /stock?name= query string."""
    key = symbol_or_name.strip().upper()
    lookup = registry_manager.get_api_name_by_symbol()
    if key in lookup:
        return lookup[key]
    if company_name_hint:
        return company_name_hint
    return symbol_or_name


class IndianAPIClient(BaseAPIClient):
    """Thin wrapper around IndianAPI.in stock endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.environ.get("INDIAN_API_KEY")
        if not self.api_key:
            raise ValueError("INDIAN_API_KEY is required (env var or constructor argument)")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: URLCache = URLCache(directory="data/raw/indianapi", format="json")
        self.registry_manager = RegistryManager()

    def _request(self, path: str, params: dict[str, str]) -> Any:
        global _request_count
        _request_count += 1
        qs = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}?{qs}"
        req = urllib.request.Request(
            url,
            headers={"x-api-key": self.api_key, "Accept": "application/json"},
        )
        logger.info(
            "IndianAPI request #%d GET %s params=%s",
            _request_count,
            path,
            params,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise IndianAPIError(f"HTTP {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise IndianAPIError(f"Network error for {path}: {exc}") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise IndianAPIError(f"Invalid JSON from {path}") from exc

        if isinstance(data, dict) and data.get("error"):
            raise IndianAPIError(f"{str(data['error'])} for {path}")
        return data

    def _fetch_stock_raw(self, name: str, *, use_cache: bool = True) -> dict[str, Any]:
        cached_data = self._cache.get(f"stock_{name}") if use_cache else None
        if cached_data is not None:
            return cached_data
        data = self._request("/stock", {"name": name})
        if not isinstance(data, dict):
            raise IndianAPIError(f"Unexpected /stock response type: {type(data).__name__}")
        if use_cache:
            self._cache.set(f"stock_{name}", data)
        return data

    def fetch_company(self, name: str) -> pd.DataFrame:
        """Return one row DataFrame aligned with ``companies`` schema (minus ``company_id``)."""
        resolved = resolve_api_name(self.registry_manager, name)
        payload = self._fetch_stock_raw(resolved)
        profile = payload.get("companyProfile") or {}

        nse = profile.get("exchangeCodeNse")
        bse = profile.get("exchangeCodeBse")
        if nse:
            symbol, exchange = str(nse), "NSE"
        elif bse:
            symbol, exchange = str(bse), "BSE"
        else:
            symbol, exchange = resolved.upper(), "NSE"

        shares_outstanding = None
        shares_diluted = None
        periods = payload.get("financials") or payload.get("stockFinancialData") or []
        if periods and isinstance(periods, list):
            latest = periods[0]
            sfm = latest.get("stockFinancialMap") or {}
            bal = rows_to_dict(sfm.get("BAL"))
            inc = rows_to_dict(sfm.get("INC"))
            raw_shares = coalesce(bal, "TotalCommonSharesOutstanding")
            if raw_shares is not None:
                shares_outstanding = int(raw_shares)
            raw_diluted = coalesce(inc, "DilutedWeightedAverageShares")
            if raw_diluted is not None:
                shares_diluted = int(raw_diluted)

        return pd.DataFrame([{
            "symbol": symbol,
            "exchange": exchange,
            "country": "India",
            "isin": profile.get("isInId"),
            "company_name": payload.get("companyName") or resolved,
            "sector": profile.get("mgSector"),
            "industry": payload.get("industry") or profile.get("mgIndustry"),
            "shares_outstanding": shares_outstanding,
            "shares_diluted": shares_diluted,
            "listing_date": None,
            "is_active": True,
            "source": SOURCE,
        }])

    def _iter_statement_periods(self, name: str) -> list[dict[str, Any]]:
        resolved = resolve_api_name(self.registry_manager, name)
        payload = self._fetch_stock_raw(resolved)
        periods = payload.get("financials") or payload.get("stockFinancialData")
        if not periods:
            return []
        if not isinstance(periods, list):
            raise IndianAPIError("financials is not a list")
        return periods

    def fetch_financials(self, name: str) -> pd.DataFrame:
        """Parse income statement periods into a ``financials``-shaped DataFrame."""
        rows: list[dict[str, Any]] = []
        for period in self._iter_statement_periods(name):
            sfm = period.get("stockFinancialMap") or {}
            inc = rows_to_dict(sfm.get("INC"))
            row = {**period_metadata(period), **map_fields(inc, self.registry_manager.get_income_statement_keys())}
            row["source"] = SOURCE
            rows.append(row)
        return pd.DataFrame(rows)

    def fetch_balance_sheets(self, name: str) -> pd.DataFrame:
        """Parse balance sheet periods into a ``balance_sheets``-shaped DataFrame."""
        rows: list[dict[str, Any]] = []
        for period in self._iter_statement_periods(name):
            sfm = period.get("stockFinancialMap") or {}
            bal = rows_to_dict(sfm.get("BAL"))
            row = {**period_metadata(period), **map_fields(bal, self.registry_manager.get_balance_sheet_keys())}

            total_assets = row.get("total_assets")
            current_assets = row.get("current_assets")
            if total_assets is not None and current_assets is not None:
                row["non_current_assets"] = total_assets - current_assets

            total_liabilities = row.get("total_liabilities")
            current_liabilities = row.get("current_liabilities")
            if total_liabilities is not None and current_liabilities is not None:
                row["non_current_liabilities"] = total_liabilities - current_liabilities

            row["source"] = SOURCE
            rows.append(row)
        return pd.DataFrame(rows)

    def fetch_cash_flows(self, name: str) -> pd.DataFrame:
        """Parse cash flow periods into a ``cash_flows``-shaped DataFrame."""
        rows: list[dict[str, Any]] = []
        for period in self._iter_statement_periods(name):
            sfm = period.get("stockFinancialMap") or {}
            cas = rows_to_dict(sfm.get("CAS"))
            row = {**period_metadata(period), **map_fields(cas, self.registry_manager.get_cash_flow_keys())}

            ocf = row.get("operating_cash_flow")
            capex = row.get("capex")
            if ocf is not None and capex is not None:
                row["free_cash_flow"] = ocf - abs(capex)

            row["source"] = SOURCE
            rows.append(row)
        return pd.DataFrame(rows)

    def fetch_prices(
        self,
        name: str,
        *,
        period: str = "5yr",
        filter_: str = "price",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Return daily close + volume rows aligned with ``prices`` schema (minus ``company_id``)."""
        resolved = resolve_api_name(self.registry_manager, name)
        cached_data = self._cache.get(f"historical_{resolved}_{period}_{filter_}") if use_cache else None
        if cached_data is not None:
            data = cached_data
        else:
            data = self._request(
                "/historical_data",
                {"stock_name": resolved, "period": period, "filter": filter_},
            )
            if not isinstance(data, dict):
                raise IndianAPIError("historical_data response is not a dict")
            if use_cache:
                self._cache.set(f"historical_{resolved}_{period}_{filter_}", data)

        datasets = data.get("datasets") or []
        price_ds = next((d for d in datasets if d.get("metric") == "Price"), None)
        vol_ds = next((d for d in datasets if d.get("metric") == "Volume"), None)
        if not price_ds:
            return pd.DataFrame(
                columns=["trade_date", "open", "high", "low", "close", "volume", "adj_close", "source"]
            )

        vol_by_date: dict[str, int | None] = {}
        if vol_ds:
            for entry in vol_ds.get("values") or []:
                if isinstance(entry, list) and len(entry) >= 2:
                    vol_by_date[str(entry[0])] = int(entry[1])

        rows: list[dict[str, Any]] = []
        for entry in price_ds.get("values") or []:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            trade_date = date.fromisoformat(str(entry[0]))
            rows.append(
                {
                    "trade_date": trade_date,
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": float(str(entry[1])),
                    "volume": vol_by_date.get(str(entry[0])),
                    "adj_close": None,
                    "source": SOURCE,
                }
            )
        return pd.DataFrame(rows)

    def fetch_corporate_actions(self, name: str, use_cache: bool = True) -> pd.DataFrame:
        """Parse corporate actions into a ``corporate_actions``-shaped DataFrame."""
        resolved = resolve_api_name(self.registry_manager, name)
        cached_data = self._cache.get(f"corporate_actions_{resolved}") if use_cache else None
        if cached_data is not None:
            data = cached_data
        else:
            data = self._request("/corporate_actions", {"stock_name": resolved})
            if not isinstance(data, dict):
                raise IndianAPIError("corporate_actions response is not a dict")
            if use_cache:
                self._cache.set(f"corporate_actions_{resolved}", data)

        rows: list[dict[str, Any]] = []

        def append_rows(section: str, action_type: str, items: list[Any] | None) -> None:
            if not items:
                return
            for item in items:
                if not isinstance(item, list) or not item:
                    continue
                action_date = parse_action_date(str(item[0]))
                if action_date is None:
                    continue
                row: dict[str, Any] = {
                    "action_date": action_date,
                    "action_type": action_type,
                    "ex_date": action_date,
                    "record_date": parse_action_date(str(item[1])) if len(item) > 1 else None,
                    "payment_date": None,
                    "currency": DEFAULT_CURRENCY,
                    "amount": None,
                    "ratio_from": None,
                    "ratio_to": None,
                    "description": None,
                    "source": SOURCE,
                }
                if action_type == "dividend" and len(item) > 3:
                    row["description"] = str(item[3])
                    row["amount"] = parse_dividend_amount(row["description"])
                elif action_type in {"bonus", "split"} and len(item) > 2:
                    ratio_text = str(item[2])
                    row["description"] = ratio_text
                    row["ratio_from"], row["ratio_to"] = parse_ratio(ratio_text)
                rows.append(row)

        for section, action_type in (
            ("dividends", "dividend"),
            ("splits", "split"),
            ("bonus", "bonus"),
        ):
            wrapper = data.get(section) or {}
            append_rows(section, action_type, wrapper.get("data") if isinstance(wrapper, dict) else None)

        return pd.DataFrame(rows)
