"""Base API client with retry logic for stock data fetching."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import pandas as pd
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class APIClientError(Exception):
    """Raised when an API returns an error payload or HTTP failure."""


class BaseAPIClient(ABC):
    """Abstract base client with retry logic for API interactions.

    Subclasses implement specific API endpoints while inheriting:
    - Automatic retries with exponential backoff
    - Structured logging
    - Error handling
    """

    def __init__(
        self,
        base_url : str,
        timeout : float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        backoff_max: float = 60.0,
    ) -> None:
        """Initialize API client with retry configuration.

        Args:
            base_url: The API base url.
            timeout: How long to wait for the response.
            max_retries: Maximum number of retry attempts.
            backoff_factor: Exponential backoff multiplier.
            backoff_max: Maximum backoff interval in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.client_name = self.__class__.__name__
    
    def _retry_wrapper(self, func, *args: Any, **kwargs: Any) -> Any:
        """Execute function with exponential backoff retries.

        Args:
            func: Callable to execute with retries.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Return value of func.

        Raises:
            Exception: If all retries are exhausted.
        """
        for attempt in Retrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=self.backoff_factor,
                max=self.backoff_max,
            ),
            reraise=True,
        ):
            with attempt:
                logger.debug(
                    "%s: Attempt %d/%d for %s",
                    self.client_name,
                    attempt.retry_state.attempt_number,
                    self.max_retries,
                    func.__name__,
                )
                return func(*args, **kwargs)

    def _headers(self) -> dict[str, str]:
        """Default request headers. Subclasses override for auth etc."""
        return {"Accept": "application/json"}

    def _request_error(self, message: str) -> Exception:
        """Build an exception for request failures. Subclasses may override."""
        return APIClientError(message)

    def _validate_response(self, data: Any, path: str) -> None:
        """Optional response-body validation. Default: no-op."""

    def _before_request(self, path: str, params: dict[str, str]) -> None:
        """Hook called before each request (logging, counters, etc.)."""
        logger.info("%s GET %s params=%s", self.client_name, path, params)

    def _request(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET ``path`` with query ``params`` and return parsed JSON.

        Args:
            path: URL path relative to ``base_url`` (e.g. ``"/stock"``).
            params: Query string parameters.
            headers: Optional request headers; defaults to :meth:`_headers`.
        """
        params = params or {}
        qs = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if qs:
            url = f"{url}?{qs}"
        req = urllib.request.Request(
            url,
            headers=headers if headers is not None else self._headers(),
        )
        self._before_request(path, params)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise self._request_error(f"HTTP {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise self._request_error(f"Network error for {path}: {exc}") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise self._request_error(f"Invalid JSON from {path}") from exc

        self._validate_response(data, path)
        return data


    # TODO: Right now these functions work on name because that is what the IndianAPI client uses.
    # But we should make them work on ticker instead, and then resolve to name internally.

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
