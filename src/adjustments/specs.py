"""Saved preferences → adjustment specs (pure; callers read the DB)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentSpec
from src.adjustments.registry import ADJUSTMENT_ORDER, get_adjustment_type


def _applies_by_default(type_id: str) -> bool:
    return getattr(get_adjustment_type(type_id), "APPLIES_BY_DEFAULT", False)


def from_prefs(prefs: pd.DataFrame) -> list[AdjustmentSpec]:
    saved = set() if prefs.empty else set(prefs["adjustment_type"])
    specs = []
    for type_id in ADJUSTMENT_ORDER:
        if type_id in saved:
            rows = prefs[prefs["adjustment_type"] == type_id]
            specs.append(get_adjustment_type(type_id).from_prefs(rows))
        elif _applies_by_default(type_id):
            specs.append(AdjustmentSpec(type_id, {}))
    return specs


def describe(specs: list[AdjustmentSpec]) -> list[dict[str, Any]]:
    """Note entries for ``specs``; a type's ``describe`` returns None to opt out."""
    described = (get_adjustment_type(s.type_id).describe(s) for s in specs)
    return [d for d in described if d is not None]
