"""Saved preferences → adjustment specs (pure; callers read the DB)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentSpec
from src.adjustments.registry import ADJUSTMENT_ORDER, get_adjustment_type


def from_prefs(prefs: pd.DataFrame) -> list[AdjustmentSpec]:
    """One spec per type with saved rows, plus an empty-params spec for each
    type that declares ``APPLIES_BY_DEFAULT`` and has none."""
    saved = set() if prefs.empty else set(prefs["adjustment_type"])
    specs = []
    for type_id in ADJUSTMENT_ORDER:
        adjustment = get_adjustment_type(type_id)
        if type_id in saved:
            rows = prefs[prefs["adjustment_type"] == type_id]
            specs.append(adjustment.from_prefs(rows))
        elif getattr(adjustment, "APPLIES_BY_DEFAULT", False):
            specs.append(AdjustmentSpec(type_id, {}))
    return specs


def describe(specs: list[AdjustmentSpec]) -> list[dict[str, Any]]:
    """Labels for the adjustments note; a by-default type with no saved
    choices changes nothing the user picked, so it is left out."""
    return [
        get_adjustment_type(s.type_id).describe(s)
        for s in specs
        if s.params
        or not getattr(get_adjustment_type(s.type_id), "APPLIES_BY_DEFAULT", False)
    ]
