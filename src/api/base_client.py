"""Base API client with retry logic for stock data fetching."""

from __future__ import annotations

import logging
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


class BaseAPIClient(ABC):
    """Abstract base client with retry logic for API interactions.

    Subclasses implement specific API endpoints while inheriting:
    - Automatic retries with exponential backoff
    - Structured logging
    - Error handling
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        backoff_max: float = 60.0,
    ) -> None:
        """Initialize API client with retry configuration.

        Args:
            max_retries: Maximum number of retry attempts.
            backoff_factor: Exponential backoff multiplier.
            backoff_max: Maximum backoff interval in seconds.
        """
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

    @abstractmethod
    def fetch(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
        """Fetch data and return as DataFrame.

        Must be implemented by subclasses.

        Returns:
            Pandas DataFrame with fetched data.
        """
        pass
