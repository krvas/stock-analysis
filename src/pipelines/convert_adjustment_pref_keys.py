"""Pipeline: re-key ``adjustment_preferences`` from concept names to row ids.

Older wizard saves stored a ``standard_concept`` (or bare ``concept``) in
``adjustment_preferences.base_concept``; the wizard now keys preferences by
the row id formed by :func:`src.models.statement.get_row_id`. For every
stored preference this CLI loads the ticker's statement set, and:

- ``base_concept`` already equals a row id in the preference's statement →
  already converted, left alone (so re-runs are no-ops);
- else exactly one non-dimensional row whose ``standard_concept`` equals it
  (falling back to ``concept``) → re-keyed to that row's ``row_id``, read
  from the :class:`~src.models.statement.Statement` (never formed here);
- zero or several matches, or a target key that already exists → logged
  and left untouched.

All renames are applied in one transaction through
:class:`~src.database.wizard_manager.WizardDatabaseManager`.

Usage::

    python -m src.pipelines.convert_adjustment_pref_keys [--dry-run]
        [--ticker T ...] [--period annual|quarterly]
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from src.api.edgartools.source import PeriodType, load_statement_set
from src.config import DEFAULT_WIZARD_DB_PATH
from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import Statement, StatementSet, StatementType

logger = logging.getLogger(__name__)

PERIOD_TYPES: tuple[PeriodType, ...] = ("annual", "quarterly")

# ``base_concept_statement`` codes allowed by wizard.sql → statement type.
STATEMENT_CODES: dict[str, StatementType] = {
    "PL": "income",
    "BS": "balance",
    "CF": "cashflow",
}

Outcome = Literal[
    "converted", "already", "unmatched", "ambiguous", "conflict", "failed"
]
OUTCOMES: tuple[Outcome, ...] = (
    "converted",
    "already",
    "unmatched",
    "ambiguous",
    "conflict",
    "failed",
)

StatementSetLoader = Callable[[str, PeriodType], StatementSet]


@dataclass(frozen=True)
class KeyConversion:
    """Planned outcome for one stored preference."""

    adjustment_id: str
    ticker: str
    adjustment_type: str
    old_key: str
    outcome: Outcome
    new_key: str | None = None


def _candidate_row_ids(statement: Statement, key: str) -> list[str]:
    """Non-dimensional row ids matching ``key`` by ``standard_concept``, else by
    ``concept`` (the same order the pre-row-id lookup used)."""
    matches = statement.find(standard_concept=key)
    if matches.empty:
        matches = statement.find(concept=key)
    return matches["row_id"].astype(str).tolist()


def _classify(
    pref: pd.Series, statement: Statement, taken: set[tuple[str, ...]]
) -> KeyConversion:
    old_key = str(pref["base_concept"])
    base = {
        "adjustment_id": str(pref["adjustment_id"]),
        "ticker": str(pref["ticker"]),
        "adjustment_type": str(pref["adjustment_type"]),
        "old_key": old_key,
    }
    if statement.frame["row_id"].eq(old_key).any():
        return KeyConversion(**base, outcome="already")

    candidates = _candidate_row_ids(statement, old_key)
    if not candidates:
        logger.warning(
            "%s %s %r (id %s): no row with that standard_concept/concept; left as is",
            base["ticker"],
            base["adjustment_type"],
            old_key,
            base["adjustment_id"],
        )
        return KeyConversion(**base, outcome="unmatched")
    if len(candidates) > 1:
        logger.warning(
            "%s %s %r (id %s): ambiguous, matches rows %s; left as is",
            base["ticker"],
            base["adjustment_type"],
            old_key,
            base["adjustment_id"],
            candidates,
        )
        return KeyConversion(**base, outcome="ambiguous")

    new_key = candidates[0]
    target = (
        str(pref["ticker"]),
        str(pref["exchange"]),
        str(pref["adjustment_type"]),
        new_key,
    )
    if target in taken:
        logger.warning(
            "%s %s %r (id %s): target key %r already exists; left as is",
            base["ticker"],
            base["adjustment_type"],
            old_key,
            base["adjustment_id"],
            new_key,
        )
        return KeyConversion(**base, outcome="conflict", new_key=new_key)
    return KeyConversion(**base, outcome="converted", new_key=new_key)


def plan_conversions(
    prefs: pd.DataFrame,
    period: PeriodType,
    load_set: StatementSetLoader = load_statement_set,
) -> list[KeyConversion]:
    """Classify every preference in ``prefs``; loads each ticker's set once."""
    taken: set[tuple[str, ...]] = {
        (
            str(p["ticker"]),
            str(p["exchange"]),
            str(p["adjustment_type"]),
            str(p["base_concept"]),
        )
        for _, p in prefs.iterrows()
    }
    sets: dict[str, StatementSet | None] = {}
    plan: list[KeyConversion] = []
    for _, pref in prefs.iterrows():
        ticker = str(pref["ticker"])
        failed = KeyConversion(
            adjustment_id=str(pref["adjustment_id"]),
            ticker=ticker,
            adjustment_type=str(pref["adjustment_type"]),
            old_key=str(pref["base_concept"]),
            outcome="failed",
        )
        code = str(pref["base_concept_statement"])
        statement_type = STATEMENT_CODES.get(code)
        if statement_type is None:
            logger.warning(
                "%s id %s: unknown base_concept_statement %r; left as is",
                ticker,
                failed.adjustment_id,
                code,
            )
            plan.append(failed)
            continue
        if ticker not in sets:
            try:
                sets[ticker] = load_set(ticker, period)
            except Exception:
                logger.exception("Could not load %s %s statements", ticker, period)
                sets[ticker] = None
        statement_set = sets[ticker]
        if statement_set is None:
            plan.append(failed)
            continue

        conversion = _classify(pref, statement_set.get(statement_type), taken)
        if conversion.outcome == "converted":
            taken.discard(
                (
                    ticker,
                    str(pref["exchange"]),
                    conversion.adjustment_type,
                    conversion.old_key,
                )
            )
            taken.add(
                (
                    ticker,
                    str(pref["exchange"]),
                    conversion.adjustment_type,
                    str(conversion.new_key),
                )
            )
        plan.append(conversion)
    return plan


def convert_pref_keys(
    *,
    tickers: Sequence[str] | None = None,
    period: PeriodType = "annual",
    dry_run: bool = False,
    db_path: Path | str = DEFAULT_WIZARD_DB_PATH,
    load_set: StatementSetLoader = load_statement_set,
) -> Counter[str]:
    """Plan and (unless ``dry_run``) apply the re-keying; returns outcome counts."""
    with WizardDatabaseManager(db_path, read_only=dry_run) as db:
        prefs = db.read_all_adjustment_preferences()
        if tickers:
            wanted = {t.upper() for t in tickers}
            prefs = prefs[prefs["ticker"].str.upper().isin(wanted)]
        plan = plan_conversions(prefs, period, load_set)

        renames = {
            c.adjustment_id: str(c.new_key) for c in plan if c.outcome == "converted"
        }
        for c in plan:
            if c.outcome == "converted":
                logger.info(
                    "%s %s (id %s): %r -> %r%s",
                    c.ticker,
                    c.adjustment_type,
                    c.adjustment_id,
                    c.old_key,
                    c.new_key,
                    " [dry run]" if dry_run else "",
                )
        if renames and not dry_run:
            db.rename_adjustment_preference_keys(renames)

    counts: Counter[str] = Counter({outcome: 0 for outcome in OUTCOMES})
    counts.update(c.outcome for c in plan)
    logger.info(
        "Summary%s: %s",
        " (dry run, nothing written)" if dry_run else "",
        ", ".join(f"{outcome}={counts[outcome]}" for outcome in OUTCOMES),
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Re-key adjustment_preferences.base_concept from standard_concept/"
            "concept names to get_row_id row ids."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log planned changes without writing.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        help="Only convert this ticker's preferences (repeatable). Default: all.",
    )
    parser.add_argument(
        "--period",
        choices=PERIOD_TYPES,
        default="annual",
        help="Statement period type to resolve rows against (default: annual).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level, format="%(levelname)s: %(name)s: %(message)s"
    )
    convert_pref_keys(tickers=args.ticker, period=args.period, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
