"""Saved preferences → adjustment specs (pure; callers read the DB)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentRun, AdjustmentSpec
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


def _describe(spec: AdjustmentSpec) -> dict[str, Any] | None:
    return get_adjustment_type(spec.type_id).describe(spec)


def describe(run: AdjustmentRun) -> dict[str, list[dict[str, Any]]]:
    """The adjustments note: what applied and what was skipped, with reasons.

    Applied entries describe only the part of each spec that applied. A skipped
    entry names the type without a count, since its spec's count would include
    the parts that applied. A type's ``describe`` returns None to leave a spec
    out of both lists.
    """
    applied = [_describe(spec) for spec in run.applied]
    return {
        "applied": [entry for entry in applied if entry is not None],
        "skipped": [
            {
                "type": skip.spec.type_id,
                "label": get_adjustment_type(skip.spec.type_id).LABEL,
                "reason": skip.reason,
            }
            for skip in run.skipped
            if _describe(skip.spec) is not None
        ],
    }
