"""Pure parsing helpers for Alpha Vantage payloads."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Final

logger = logging.getLogger(__name__)

DEFAULT_CURRENCY: Final[str] = "USD"
SOURCE: Final[str] = "alphavantage"


def parse_number(value: Any) -> float | None:
    """Convert Alpha Vantage numeric strings (or ``None`` / ``\"None\"``) to float."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "none" or text == "-":
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        logger.debug("Unparseable Alpha Vantage number: %r", value)
        return None


def parse_int(value: Any) -> int | None:
    """Convert a numeric string to int, discarding fractional parts."""
    number = parse_number(value)
    if number is None:
        return None
    return int(number)


def parse_date(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date string."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "none":
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        logger.debug("Unparseable Alpha Vantage date: %r", value)
        return None


def period_metadata(report: dict[str, Any], period_type: str) -> dict[str, Any]:
    """Build normalized period columns from an Alpha Vantage statement report."""
    end = parse_date(report.get("fiscalDateEnding"))
    if end is None:
        raise ValueError(f"Missing fiscalDateEnding in report: {report!r}")
    fiscal_quarter = ((end.month - 1) // 3) + 1 if period_type == "quarterly" else None
    currency = report.get("reportedCurrency") or DEFAULT_CURRENCY
    return {
        "period_end_date": end,
        "period_type": period_type,
        "fiscal_year": end.year,
        "fiscal_quarter": fiscal_quarter,
        "currency": str(currency),
    }


def parse_split_factor(factor: str | None) -> tuple[int | None, int | None]:
    """Parse Alpha Vantage ``split_factor`` (e.g. ``\"4/1\"``) into ``(ratio_from, ratio_to)``.

    ``\"A/B\"`` means A new shares for B old shares → ``ratio_from=B``, ``ratio_to=A``.
    """
    if not factor:
        return None, None
    text = str(factor).strip()
    if "/" not in text:
        return None, None
    left, right = text.split("/", 1)
    try:
        ratio_to = int(float(left.strip()))
        ratio_from = int(float(right.strip()))
    except ValueError:
        logger.debug("Unparseable split factor: %r", factor)
        return None, None
    return ratio_from, ratio_to
