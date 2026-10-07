"""Load a ticker's saved adjustments and apply them to its statements.

The web-layer I/O half of the adjustments pipeline: reads prefs from
``wizard.duckdb`` and calls the pure engine (``src/adjustments``).
"""

from __future__ import annotations

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments
from src.adjustments.specs import from_prefs
from src.api.edgartools.source import load_statement_set
from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import PeriodType, StatementSet

# The wizard route layer only supports a single exchange for now; the DB
# layer has a real exchange column, but nothing above it threads a value
# through.
DEFAULT_EXCHANGE = "NASDAQ"


def load_specs(ticker: str) -> list[AdjustmentSpec]:
    with WizardDatabaseManager(read_only=True) as db:
        prefs = db.read_adjustment_preferences(ticker, DEFAULT_EXCHANGE)
    return from_prefs(prefs)


def load_adjusted(
    ticker: str, period: PeriodType, until: str | None = None
) -> tuple[StatementSet, StatementSet, list[AdjustmentSpec]]:
    """``(reported, adjusted, specs)``; ``until`` stops before that type."""
    base = load_statement_set(ticker, period)
    specs = load_specs(ticker)
    return base, apply_adjustments(base, specs, until=until), specs
