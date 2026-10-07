"""Saved preferences → adjustment specs (pure; callers read the DB)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentSpec
from src.adjustments.registry import ADJUSTMENT_ORDER, get_adjustment_type


def from_prefs(prefs: pd.DataFrame) -> list[AdjustmentSpec]:
    """One spec per adjustment type present in ``adjustment_preferences`` rows."""
    if prefs.empty:
        return []
    return [
        get_adjustment_type(type_id).from_prefs(
            prefs[prefs["adjustment_type"] == type_id]
        )
        for type_id in ADJUSTMENT_ORDER
        if (prefs["adjustment_type"] == type_id).any()
    ]


def describe(specs: list[AdjustmentSpec]) -> list[dict[str, Any]]:
    return [get_adjustment_type(s.type_id).describe(s) for s in specs]
