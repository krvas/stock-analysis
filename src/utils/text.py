"""Small text/missing-value helpers shared across modules."""

from __future__ import annotations

import pandas as pd


def is_missing(value: object) -> bool:
    """Whether ``value`` is a scalar missing marker (None / NaN / NA)."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # list-like values: not a scalar missing marker
        return False


def clean_str(value: object) -> str | None:
    """``value`` as a stripped string; ``None`` when missing or blank."""
    if is_missing(value):
        return None
    text = str(value).strip()
    return text or None
