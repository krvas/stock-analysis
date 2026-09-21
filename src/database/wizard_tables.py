"""Table names and column definitions aligned with wizard.sql."""

from __future__ import annotations

from typing import Final

ADJUSTMENT_PREFERENCES: Final[str] = "adjustment_preferences"

ALL_TABLES: Final[tuple[str, ...]] = (ADJUSTMENT_PREFERENCES,)

PRIMARY_KEYS: Final[dict[str, tuple[str, ...]]] = {
    ADJUSTMENT_PREFERENCES: ("adjustment_id",),
}

UNIQUE_KEYS: Final[dict[str, tuple[str, ...]]] = {
    ADJUSTMENT_PREFERENCES: ("ticker", "exchange", "adjustment_type", "base_concept"),
}

TABLE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    ADJUSTMENT_PREFERENCES: (
        "adjustment_id",
        "ticker",
        "exchange",
        "statement",
        "adjustment_type",
        "base_concept",
        "base_concept_statement",
        "value",
        "consolidated_ids",
        "updated_at",
    ),
}

SCHEMA_DEFAULTS: Final[dict[str, dict[str, object]]] = {}
