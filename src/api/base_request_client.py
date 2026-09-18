"""Request-level HTTP client utilities with retry/backoff.

This module provides `APIClientError` and `BaseRequestClient` which handle
low-level URL requests, retries, headers, and JSON parsing. Higher-level
API clients that expose domain-specific methods should subclass
`BaseAPIClient` in `base_client.py`.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from tenacity import Retrying, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    """Raised when an API returns an error payload or HTTP failure."""


class BaseRequestClient:
    """Light-weight client focused on making HTTP requests with retries.

    This class intentionally contains no domain-specific abstract methods;
    it's suitable as a base for API-specific classes that only need HTTP
    behavior.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        backoff_max: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.client_name = self.__class__.__name__

    def _retry_wrapper(self, func, *args: Any, **kwargs: Any) -> Any:
        for attempt in Retrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff_factor, max=self.backoff_max),
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
        return {"Accept": "application/json"}

    def _request_error(self, message: str) -> Exception:
        return APIClientError(message)

    def _validate_response(self, data: Any, path: str) -> None:
        """Optional response-body validation. Default: no-op."""

    def _before_request(self, path: str, params: dict[str, str]) -> None:
        logger.info("%s GET %s params=%s", self.client_name, path, params)

    def _request(self, path: str, params: dict[str, str] | None = None, *, headers: dict[str, str] | None = None) -> Any:
        params = params or {}
        qs = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if qs:
            url = f"{url}?{qs}"
        req = urllib.request.Request(url, headers=headers if headers is not None else self._headers())
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
