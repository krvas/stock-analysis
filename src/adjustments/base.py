"""Value types shared by the adjustments engine and adjustment types.

Pure: no I/O. See ``specs/adjustments_architecture.md`` §2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.models.statement import StatementType


@dataclass(frozen=True)
class AdjustmentSpec:
    """One saved (or draft) adjustment: its type and type-specific params."""

    type_id: str
    params: Mapping[str, Any]


@dataclass(frozen=True)
class NewRow:
    """A row an adjustment inserts into one statement.

    ``parent_concept`` / ``weight`` wire the row into the calc tree of every
    period whose tree contains ``parent_concept``; with no parent the row is a
    memo row (shown, never summed). ``values`` are raw-sign period values.
    """

    statement: StatementType
    concept: str
    label: str
    values: Mapping[str, float]
    parent_concept: Mapping[str, str] | str | None = None
    weight: float = 1.0
    tags: tuple[str, ...] = ()
    after: str | None = None
    is_total: bool = False


@dataclass(frozen=True)
class Override:
    """Replace one existing row's period values (raw signs)."""

    statement: StatementType
    row_id: str
    values: Mapping[str, float]


@dataclass
class AdjustmentResult:
    new_rows: list[NewRow] = field(default_factory=list)
    overrides: list[Override] = field(default_factory=list)
