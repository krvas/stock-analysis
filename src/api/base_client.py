"""High-level API client base class built on top of request utilities.

`BaseAPIClient` provides the abstract surface expected by downstream
API-specific clients (fetch_company, fetch_financials, etc.) while
delegating low-level HTTP behavior to `BaseRequestClient` in
`base_request_client.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

import pandas as pd

from .base_request_client import APIClientError, BaseRequestClient

T = TypeVar("T")


class BaseAPIClient(BaseRequestClient, ABC):
    """Abstract base client with domain-specific abstract methods.

    This class intentionally only defines the abstract API surface; all
    HTTP, retry, and JSON parsing behavior is implemented in
    `BaseRequestClient`.
    """

    @abstractmethod
    def fetch_company(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Fetch company metadata as a DataFrame.

        Expected to return a single-row DataFrame aligned with the project's
        companies schema (minus company_id).
        """

    @abstractmethod
    def fetch_financials(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Fetch income statement periods as a DataFrame."""

    @abstractmethod
    def fetch_balance_sheets(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Fetch balance sheet periods as a DataFrame."""

    @abstractmethod
    def fetch_cash_flows(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Fetch cash flow periods as a DataFrame."""

    @abstractmethod
    def fetch_prices(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Fetch time series price rows as a DataFrame."""

    @abstractmethod
    def fetch_corporate_actions(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Fetch corporate actions (dividends, splits, bonuses) as a DataFrame."""
