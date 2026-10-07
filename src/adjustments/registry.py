"""Adjustment type identity and pipeline order (identity only, no logic)."""

from __future__ import annotations

from types import ModuleType

from src.adjustments.types import opex_to_capex, owner_earnings

ADJUSTMENT_TYPES: dict[str, ModuleType] = {
    opex_to_capex.TYPE_ID: opex_to_capex,
    owner_earnings.TYPE_ID: owner_earnings,
}

# Pipeline order: each type sees the output of the ones before it.
ADJUSTMENT_ORDER: tuple[str, ...] = (opex_to_capex.TYPE_ID, owner_earnings.TYPE_ID)


def get_adjustment_type(type_id: str) -> ModuleType:
    return ADJUSTMENT_TYPES[type_id]
