"""Load a ticker's saved adjustments and apply them to its statements.

The web-layer I/O half of the adjustments pipeline: reads prefs from
``wizard.duckdb`` and calls the pure engine (``src/adjustments``).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.specs import from_prefs
from src.api.edgartools.source import load_statement_set
from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import PeriodType, StatementSet
from src.web.settings import Basis

# The wizard route layer only supports a single exchange for now; the DB
# layer has a real exchange column, but nothing above it threads a value
# through.
DEFAULT_EXCHANGE = "NASDAQ"


def load_specs(ticker: str) -> list[AdjustmentSpec]:
    with WizardDatabaseManager(read_only=True) as db:
        prefs = db.read_adjustment_preferences(ticker, DEFAULT_EXCHANGE)
    return from_prefs(prefs)


@dataclass(frozen=True)
class Loaded:
    statements: StatementSet
    specs: list[AdjustmentSpec]


def load_for_basis(
    ticker: str, period: PeriodType, basis: Basis, *, until: str | None = None
) -> Loaded:
    """``until`` stops the adjusted set before that adjustment type."""
    reported = load_statement_set(ticker, period)
    if basis == "reported":
        return Loaded(reported, [])
    specs = load_specs(ticker)
    return Loaded(apply_adjustments(reported, specs, until=until), specs)
