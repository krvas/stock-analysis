"""Pure parsing helpers for IndianAPI.in statement and corporate-action payloads."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Final

logger = logging.getLogger(__name__)

DEFAULT_CURRENCY: Final[str] = "INR"
SKIP_KEYS: Final[frozenset[str]] = frozenset({"periodType", "periodLength"})
FISCAL_QUARTER_BY_MONTH: Final[dict[int, int]] = {6: 1, 9: 2, 12: 3, 3: 4}


def parse_amount(value: str | None, key: str) -> float | None:
    """Convert a raw amount string into a float, ignoring empty or skipped values."""
    if key in SKIP_KEYS:
        return None
    if value is None:
        return None
    text = value.strip()
    if text == "" or text == "-":
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        logger.debug("Unparseable amount for key=%s value=%r", key, value)
        return None


def rows_to_dict(rows: list[dict[str, Any]] | None) -> dict[str, float | None]:
    """Turn a list of row dictionaries into a simple key-to-amount mapping."""
    if not rows:
        return {}
    return {
        str(row["key"]): parse_amount(row.get("value"), str(row["key"]))
        for row in rows
        if isinstance(row, dict) and row.get("key") not in SKIP_KEYS
    }


def coalesce(row: dict[str, float | None], *keys: str) -> float | None:
    """Return the first non-None value from a list of candidate keys."""
    for key in keys:
        val = row.get(key)
        if val is not None:
            return val
    return None


def map_fields(
    row: dict[str, float | None],
    field_keys: dict[str, tuple[str, ...]],
) -> dict[str, float | None]:
    """Map a row of parsed values into a normalized field dictionary."""
    return {column: coalesce(row, *keys) for column, keys in field_keys.items()}


def period_metadata(period: dict[str, Any]) -> dict[str, Any]:
    """Build normalized metadata for a financial period from the raw payload."""
    end = date.fromisoformat(str(period["EndDate"]))
    period_type = "annual" if period.get("Type") == "Annual" else "quarterly"
    fiscal_year = int(period["FiscalYear"])
    fiscal_quarter = (
        FISCAL_QUARTER_BY_MONTH.get(end.month) if period_type == "quarterly" else None
    )
    return {
        "period_end_date": end,
        "period_type": period_type,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "currency": DEFAULT_CURRENCY,
    }


def parse_action_date(value: str | None) -> date | None:
    """Parse a corporate-action date from common string formats."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            # Source values are plain calendar dates with no timezone concept
            # (IndianAPI corporate-action payloads); forcing tz-awareness here
            # would misrepresent the data rather than fix a real bug.
            return datetime.strptime(value, fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    logger.debug("Unparseable corporate action date: %r", value)
    return None


def parse_ratio(value: str | None) -> tuple[int | None, int | None]:
    """Extract the numerator and denominator from a ratio-like string."""
    if not value:
        return None, None
    match = re.search(r"(\d+)\s*:\s*(\d+)", value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def parse_dividend_amount(description: str | None) -> float | None:
    """Extract a dividend amount from a descriptive text field."""
    if not description:
        return None
    match = re.search(r"Rs\.?\s*([\d,.]+)", description, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None
