"""Pipeline: calc-linkbase residual report over the cached edgartools bundles.

For every cached (ticker, period type, statement), computes
``reported(parent) − Σ weight·child`` per calc parent × period via
:func:`src.models.calc_residuals.calc_residuals` (raw signs) and logs a summary
plus every non-zero residual, sorted by absolute relative residual.

Reads cached bundles only — never fetches from SEC and never modifies the
cache (``load_period_bundle(prune=False)``): missing, stale or invalid
bundles are logged and skipped, not deleted.

Usage::

    python -m src.pipelines.calc_residual_report [--ticker T ...]
        [--period annual|quarterly] [--tolerance X] [--csv PATH]
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from src.api.edgartools.cache import (
    PeriodType,
    cached_companies,
    find_cached_cik,
    load_period_bundle,
)
from src.config import EDGARTOOLS_CACHE_DIR
from src.models.calc_residuals import calc_residuals
from src.models.statement import STATEMENT_TYPES, Statement

logger = logging.getLogger(__name__)

PERIOD_TYPES: tuple[PeriodType, ...] = ("annual", "quarterly")

# Absolute tolerance in reported units: XBRL monetary facts are integers, so
# anything below one unit is float noise, not a real gap.
DEFAULT_TOLERANCE = 0.5

SUMMARY_COLUMNS: tuple[str, ...] = (
    "ticker",
    "period_type",
    "statement",
    "parents",
    "parent_periods",
    "zero_share",
    "non_zero",
)

DETAIL_COLUMNS: tuple[str, ...] = (
    "ticker",
    "period_type",
    "statement",
    "row_id",
    "label",
    "period",
    "reported",
    "computed",
    "residual",
    "relative",
    "n_children",
    "n_nan_children",
)


def _companies(tickers: Sequence[str] | None, cache_dir: Path) -> dict[str, str]:
    """``{cik: ticker}`` to report on: requested tickers, else the whole index."""
    if not tickers:
        return cached_companies(cache_dir)
    companies: dict[str, str] = {}
    for ticker in tickers:
        cik = find_cached_cik(cache_dir, ticker)
        if cik is None:
            logger.warning("%s is not in the edgartools cache index; skipping", ticker)
            continue
        companies[cik] = ticker.upper()
    return companies


def collect_residuals(
    tickers: Sequence[str] | None = None,
    periods: Sequence[PeriodType] = PERIOD_TYPES,
    cache_dir: Path = EDGARTOOLS_CACHE_DIR,
) -> pd.DataFrame:
    """All parent × period residuals for the cached bundles, tagged by
    ``ticker`` / ``period_type`` / ``statement``. Cache reads only."""
    frames: list[pd.DataFrame] = []
    for cik, ticker in sorted(
        _companies(tickers, cache_dir).items(), key=lambda i: i[1]
    ):
        for period in periods:
            bundle = load_period_bundle(
                cik=cik, period=period, cache_dir=cache_dir, prune=False
            )
            if bundle is None:
                logger.warning(
                    "No usable %s bundle for %s (CIK %s); skipping", period, ticker, cik
                )
                continue
            for statement_type in STATEMENT_TYPES:
                residuals = calc_residuals(
                    Statement(bundle[statement_type], statement_type)
                )
                residuals.insert(0, "statement", statement_type)
                residuals.insert(0, "period_type", period)
                residuals.insert(0, "ticker", ticker)
                frames.append(residuals)
    if not frames:
        return pd.DataFrame(columns=["ticker", "period_type", "statement"])
    return pd.concat(frames, ignore_index=True)


def summarize(residuals: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """Per ticker × period type × statement: parents checked, parent-periods,
    share with ``|residual| <= tolerance``, and the non-zero count."""
    if residuals.empty:
        return pd.DataFrame(columns=list(SUMMARY_COLUMNS))
    flagged = residuals.assign(zero=residuals["residual"].abs() <= tolerance)
    grouped = flagged.groupby(["ticker", "period_type", "statement"], sort=True)
    summary = grouped.agg(
        parents=("row_id", "nunique"),
        parent_periods=("row_id", "size"),
        zero=("zero", "sum"),
    ).reset_index()
    summary["zero_share"] = summary["zero"] / summary["parent_periods"]
    summary["non_zero"] = summary["parent_periods"] - summary["zero"]
    return summary[list(SUMMARY_COLUMNS)]


def non_zero_residuals(residuals: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """Rows with ``|residual| > tolerance``, largest ``|relative|`` first."""
    if residuals.empty:
        return pd.DataFrame(columns=list(DETAIL_COLUMNS))
    rows = residuals[residuals["residual"].abs() > tolerance]
    order = np.argsort(-rows["relative"].abs().fillna(0.0).to_numpy(), kind="stable")
    return rows.iloc[order][list(DETAIL_COLUMNS)].reset_index(drop=True)


def _format_report(summary: pd.DataFrame, details: pd.DataFrame) -> str:
    lines = ["Calc residual summary (raw signs):"]
    if summary.empty:
        lines.append("  (no cached bundles)")
    else:
        lines.append(
            summary.to_string(index=False, formatters={"zero_share": "{:.1%}".format})
        )
        totals = summary[["parent_periods", "non_zero"]].sum()
        lines.append(
            f"Total: {int(totals['parent_periods'])} parent-periods, "
            f"{int(totals['non_zero'])} non-zero"
        )
    lines.append("")
    lines.append(f"Non-zero residuals ({len(details)}):")
    if not details.empty:
        with pd.option_context("display.width", 250, "display.max_colwidth", 70):
            lines.append(
                details.to_string(
                    index=False,
                    formatters={
                        "reported": "{:,.0f}".format,
                        "computed": "{:,.0f}".format,
                        "residual": "{:,.0f}".format,
                        "relative": "{:.4f}".format,
                    },
                )
            )
    return "\n".join(lines)


def run_report(
    tickers: Sequence[str] | None,
    periods: Sequence[PeriodType],
    tolerance: float,
    csv_path: Path | None,
) -> None:
    residuals = collect_residuals(tickers, periods)
    summary = summarize(residuals, tolerance)
    details = non_zero_residuals(residuals, tolerance)
    logger.info("\n%s", _format_report(summary, details))
    if csv_path is not None:
        details.to_csv(csv_path, index=False)
        logger.info("Wrote %d non-zero residuals to %s", len(details), csv_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report calc-linkbase residuals over cached edgartools bundles.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        help="Ticker to report on (repeatable). Default: every cached company.",
    )
    parser.add_argument(
        "--period",
        choices=PERIOD_TYPES,
        help="Period type. Default: both annual and quarterly.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=(
            "Absolute residual (reported units) counted as zero "
            f"(default: {DEFAULT_TOLERANCE})."
        ),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Also write the non-zero residuals to this CSV file.",
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
    periods = (args.period,) if args.period else PERIOD_TYPES
    run_report(args.ticker, periods, args.tolerance, args.csv)


if __name__ == "__main__":
    main()
