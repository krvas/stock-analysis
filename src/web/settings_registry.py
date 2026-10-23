"""The Settings registry: every Setting and cross-Setting rule, declared once.

Data only. The shapes live in ``src/web/setting_types.py``; the rules that
resolve, validate and render them live in ``src/web/settings.py``.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, cast, get_args

from src.config import MAX_CACHE_QUARTERS, MAX_ITEMS_PER_SIDE
from src.models.statement import PERIOD_TYPES, STATEMENT_VIEWS, Basis
from src.web.setting_types import (
    ChoiceSetting,
    CrossRule,
    IntSetting,
    Option,
)

MAX_OFFSET: Final = MAX_CACHE_QUARTERS - 1


RULES: Final[tuple[CrossRule, ...]] = (
    CrossRule(
        ids=("current_period", "previous_period"),
        holds=lambda v: (
            cast(int, v["previous_period"]) > cast(int, v["current_period"])
        ),
        # Pages share the current period, so it moves only when it sits at the
        # oldest offset and leaves no room for an older previous period.
        repair=lambda v, ceiling: {
            "current_period": min(cast(int, v["current_period"]), max(ceiling - 1, 0)),
            "previous_period": min(cast(int, v["current_period"]) + 1, ceiling),
        },
        message="Previous period must be older than the current period",
    ),
)


class GlobalSetting(Enum):
    """The Global Settings, in drawer order; each member's value is its Setting."""

    PERIOD = ChoiceSetting(
        "period",
        "Period type",
        tuple(Option(p, p.capitalize()) for p in PERIOD_TYPES),
        "annual",
    )
    NUM_PERIODS = IntSetting(
        "num_periods", "Number of periods", 1, MAX_CACHE_QUARTERS, 10
    )
    VIEW = ChoiceSetting(
        "view",
        "View",
        tuple(Option(v, v.capitalize()) for v in STATEMENT_VIEWS),
        "standard",
        instant=True,
    )


class SubpageSetting(Enum):
    """The Sub-page Settings, in drawer order; each member's value is its Setting."""

    BASIS = ChoiceSetting(
        "basis",
        "Basis",
        tuple(Option(b, b.capitalize()) for b in get_args(Basis)),
        "reported",
    )
    CURRENT_PERIOD = IntSetting(
        "current_period",
        "Current period",
        0,
        MAX_OFFSET,
        0,
        widget="offset",
    )
    PREVIOUS_PERIOD = IntSetting(
        "previous_period",
        "Previous period",
        0,
        MAX_OFFSET,
        1,
        widget="offset",
    )
    ITEMS_PER_SIDE = IntSetting(
        "items_per_side", "Items per side", 1, MAX_ITEMS_PER_SIDE, 5
    )
