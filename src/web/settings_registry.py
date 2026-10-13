"""The Settings registry: every Setting and cross-Setting rule, declared once.

Data only. The shapes live in ``src/web/setting_types.py``; the rules that
resolve, validate and render them live in ``src/web/settings.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, cast

from src.config import MAX_CACHE_QUARTERS, MAX_ITEMS_PER_SIDE
from src.models.statement import PERIOD_TYPES, STATEMENT_VIEWS
from src.web.setting_types import (
    ChoiceSetting,
    CrossRule,
    IntSetting,
    SettingDef,
)

GLOBAL_SETTINGS: Final[tuple[SettingDef, ...]] = (
    ChoiceSetting(
        "period",
        "Period type",
        tuple((p, p.capitalize()) for p in PERIOD_TYPES),
        "annual",
    ),
    # The per-period-type cache cap is a clamp at load time, not a validation
    # bound, so switching period type never invalidates the stored count.
    IntSetting("num_periods", "Number of periods", 1, MAX_CACHE_QUARTERS, 10),
    ChoiceSetting(
        "view",
        "View",
        tuple((v, v.capitalize()) for v in STATEMENT_VIEWS),
        "standard",
        instant=True,
    ),
)
SUBPAGE_SETTINGS: Final[tuple[SettingDef, ...]] = (
    ChoiceSetting(
        "basis",
        "Basis",
        (("reported", "Reported"), ("adjusted", "Adjusted")),
        "reported",
    ),
    IntSetting(
        "current_period",
        "Current period",
        0,
        MAX_CACHE_QUARTERS - 1,
        0,
        widget="offset",
    ),
    IntSetting(
        "previous_period",
        "Previous period",
        0,
        MAX_CACHE_QUARTERS - 1,
        1,
        widget="offset",
    ),
    IntSetting("items_per_side", "Items per side", 1, MAX_ITEMS_PER_SIDE, 5),
)
SETTINGS: Final[tuple[SettingDef, ...]] = GLOBAL_SETTINGS + SUBPAGE_SETTINGS
GLOBAL_SETTING_IDS: Final[frozenset[str]] = frozenset(s.id for s in GLOBAL_SETTINGS)
SUBPAGE_SETTING_IDS: Final[frozenset[str]] = frozenset(s.id for s in SUBPAGE_SETTINGS)
SETTINGS_BY_ID: Final[Mapping[str, SettingDef]] = MappingProxyType(
    {s.id: s for s in SETTINGS}
)

RULES: Final[tuple[CrossRule, ...]] = (
    CrossRule(
        ids=("current_period", "previous_period"),
        holds=lambda v: (
            cast(int, v["previous_period"]) > cast(int, v["current_period"])
        ),
        # Keep the current period: pages share it, so it must not move.
        repair=lambda v: {"previous_period": cast(int, v["current_period"]) + 1},
        message="Previous period must be older than the current period",
    ),
)

if len(SETTINGS_BY_ID) != len(SETTINGS):
    raise RuntimeError("SETTINGS ids must be unique")
