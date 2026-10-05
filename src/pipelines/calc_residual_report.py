"""Pipeline: calc-linkbase residual report over the cached edgartools bundles.

For every cached (ticker, period type, statement), computes
``reported(parent) − Σ weight·child`` per calc parent × period via
:func:`src.models.calc_residuals.calc_residuals` (raw signs) and logs a summary
plus every non-zero residual, sorted by absolute relative residual.

By default reads cached bundles only — never fetches from SEC and never
modifies the cache (``load_period_bundle(prune=False)``): missing, stale or
invalid bundles are logged and skipped, not deleted.

``--compare-viewer`` additionally fetches each company's filings from SEC and
compares our residuals with edgartools' SEC-viewer calc validation
(``filing.viewer.validate()``), which checks only each filing's latest period
(see :func:`collect_viewer_validations`).

Usage::

    python -m src.pipelines.calc_residual_report [--ticker T ...]
        [--period annual|quarterly] [--tolerance X] [--csv PATH]
        [--compare-viewer [--viewer-filings N]]
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
from edgar import Company

from src.api.edgartools.cache import (
    PeriodType,
    cached_companies,
    find_cached_cik,
    load_period_bundle,
)
from src.api.edgartools.source import (
    FORM_BY_PERIOD,
    MAX_PERIODS_BY_PERIOD,
    setup_edgartools,
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
    "n_missing_children",
)

# ``collect_viewer_validations`` output; values in raw (unscaled) units.
VIEWER_COLUMNS: tuple[str, ...] = (
    "ticker",
    "period_type",
    "statement",
    "concept",
    "period",
    "viewer_expected",
    "viewer_computed",
    "viewer_difference",
    "viewer_valid",
)

# Columns ``compare_with_viewer`` adds to the residuals.
COMPARE_COLUMNS: tuple[str, ...] = (
    "viewer_expected",
    "viewer_computed",
    "viewer_difference",
    "viewer_valid",
    "agrees",
)

# Extra summary columns with ``--compare-viewer``.
COMPARE_SUMMARY_COLUMNS: tuple[str, ...] = (
    "matched",
    "agree",
    "ours_only",
    "viewer_only",
)

_GROUP_KEYS = ["ticker", "period_type", "statement"]
_JOIN_KEYS = [*_GROUP_KEYS, "concept", "period"]


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
                frame, calc_edges = bundle[statement_type]
                residuals = calc_residuals(
                    Statement(frame, statement_type, calc_edges=calc_edges)
                )
                residuals.insert(0, "statement", statement_type)
                residuals.insert(0, "period_type", period)
                residuals.insert(0, "ticker", ticker)
                frames.append(residuals)
    if not frames:
        return pd.DataFrame(columns=["ticker", "period_type", "statement"])
    return pd.concat(frames, ignore_index=True)


def _viewer_statement(role: str) -> str:
    """Our statement type for a viewer report short name, else ``role`` as is.

    E.g. "CONSOLIDATED STATEMENTS OF OPERATIONS" -> income; stand-alone
    comprehensive income, equity and parenthetical reports stay raw.
    """
    name = role.upper()
    if "PARENTHETICAL" in name:
        return role
    if "CASH FLOW" in name:
        return "cashflow"
    if any(k in name for k in ("BALANCE SHEET", "FINANCIAL POSITION", "CONDITION")):
        return "balance"
    name = name.replace("COMPREHENSIVE INCOME", "").replace("COMPREHENSIVE LOSS", "")
    if any(k in name for k in ("OPERATIONS", "INCOME", "EARNINGS")):
        return "income"
    return role


def collect_viewer_validations(
    ticker: str,
    period: PeriodType,
    max_filings: int | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> pd.DataFrame:
    """edgartools' SEC-viewer calc validation for ``ticker``'s filings.

    Lists filings like ``load_statement_set`` (newest ``max_filings``, default
    the bundle's :data:`MAX_PERIODS_BY_PERIOD`) and runs
    ``filing.viewer.validate(tolerance)`` on each — **network**. The viewer
    checks every calc parent of its 'Statements' reports on the filing's
    primary (latest) period only, tagged here with ``period_of_report``.

    Viewer values are parsed from the R*.htm display text, so they are in
    display units; they are multiplied by the report's ``currency_scaling``
    to match our raw XBRL units. ``viewer_valid`` is the viewer's own verdict
    (``tolerance`` in display units). Filings without a viewer (no
    MetaLinks.json) or whose validation fails are logged and skipped.
    """
    setup_edgartools()
    max_filings = max_filings or MAX_PERIODS_BY_PERIOD[period]
    filings = (
        Company(ticker)
        .get_filings(form=FORM_BY_PERIOD[period], amendments=False)
        .head(max_filings)
    )
    records: list[dict] = []
    for filing in filings:
        label = f"{ticker} {filing.form} {filing.period_of_report}"
        try:
            viewer = filing.viewer
            if viewer is None:
                logger.warning("No SEC viewer for %s; skipping", label)
                continue
            scaling = {
                report.short_name: report.currency_scaling
                for report in viewer.financial_statements
            }
            results = viewer.validate(tolerance=tolerance)
        except Exception:  # noqa: BLE001 - edgartools raises assorted errors
            logger.warning("SEC viewer validation failed for %s; skipping", label)
            continue
        for result in results:
            scale = scaling.get(result["role"], 1)
            records.append(
                {
                    "ticker": ticker.upper(),
                    "period_type": period,
                    "statement": _viewer_statement(result["role"]),
                    "concept": result["parent"].id,
                    "period": str(filing.period_of_report),
                    "viewer_expected": result["expected"] * scale,
                    "viewer_computed": result["computed"] * scale,
                    "viewer_difference": result["difference"] * scale,
                    "viewer_valid": bool(result["valid"]),
                }
            )
    return pd.DataFrame(records, columns=list(VIEWER_COLUMNS))


def compare_with_viewer(
    residuals: pd.DataFrame, viewer: pd.DataFrame, tolerance: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Left-join viewer validations onto our residuals.

    Joined on ticker / period type / statement / concept / period. Adds
    :data:`COMPARE_COLUMNS`; ``agrees`` is ``|residual − viewer_difference|
    <= tolerance`` (``None`` without a viewer match). Returns
    ``(compared, viewer_only)``, the latter the viewer rows matching none of
    ours.
    """
    viewer = viewer[list(VIEWER_COLUMNS)].drop_duplicates(_JOIN_KEYS)
    compared = residuals.merge(viewer, on=_JOIN_KEYS, how="left")
    difference = pd.to_numeric(compared["viewer_difference"]).astype(float)
    matched = difference.notna()
    agrees = (compared["residual"] - difference).abs() <= tolerance
    compared["agrees"] = agrees.astype(object).where(matched, None)
    keys = residuals[_JOIN_KEYS].drop_duplicates()
    flagged = viewer.merge(keys, on=_JOIN_KEYS, how="left", indicator=True)
    viewer_only = flagged[flagged["_merge"] == "left_only"].drop(columns="_merge")
    return compared, viewer_only.reset_index(drop=True)


def summarize_comparison(
    compared: pd.DataFrame, viewer_only: pd.DataFrame
) -> pd.DataFrame:
    """Per ticker × period type × statement: :data:`COMPARE_SUMMARY_COLUMNS`."""
    flags = compared.assign(
        matched=compared["viewer_difference"].notna(),
        agree=compared["agrees"].eq(True),
    )
    ours = (
        flags.groupby(_GROUP_KEYS)
        .agg(matched=("matched", "sum"), agree=("agree", "sum"), n=("row_id", "size"))
        .reset_index()
    )
    ours["ours_only"] = ours["n"] - ours["matched"]
    only = viewer_only.groupby(_GROUP_KEYS).size().rename("viewer_only").reset_index()
    summary = ours.merge(only, on=_GROUP_KEYS, how="outer")
    counts = list(COMPARE_SUMMARY_COLUMNS)
    summary[counts] = summary[counts].fillna(0).astype(int)
    return summary[[*_GROUP_KEYS, *counts]]


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
    return _by_relative(residuals[residuals["residual"].abs() > tolerance])[
        list(DETAIL_COLUMNS)
    ]


def flagged_residuals(compared: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """Compared rows that are non-zero or disagree with the viewer, largest
    ``|relative|`` first, with :data:`COMPARE_COLUMNS`."""
    columns = [*DETAIL_COLUMNS, *COMPARE_COLUMNS]
    if compared.empty:
        return pd.DataFrame(columns=columns)
    rows = compared[
        (compared["residual"].abs() > tolerance) | compared["agrees"].eq(False)
    ]
    return _by_relative(rows)[columns]


def _by_relative(rows: pd.DataFrame) -> pd.DataFrame:
    order = np.argsort(-rows["relative"].abs().fillna(0.0).to_numpy(), kind="stable")
    return rows.iloc[order].reset_index(drop=True)


def _format_report(summary: pd.DataFrame, details: pd.DataFrame) -> str:
    compare = "matched" in summary.columns
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
        if compare:
            viewer = summary[list(COMPARE_SUMMARY_COLUMNS)].sum()
            lines.append(
                f"SEC viewer: {viewer['matched']} matched, {viewer['agree']} agree, "
                f"{viewer['ours_only']} ours only, {viewer['viewer_only']} viewer only"
            )
    lines.append("")
    title = "Non-zero or viewer-disagreeing" if compare else "Non-zero"
    lines.append(f"{title} residuals ({len(details)}):")
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
                        "viewer_expected": "{:,.0f}".format,
                        "viewer_computed": "{:,.0f}".format,
                        "viewer_difference": "{:,.0f}".format,
                    },
                )
            )
    return "\n".join(lines)


def run_report(
    tickers: Sequence[str] | None,
    periods: Sequence[PeriodType],
    tolerance: float,
    csv_path: Path | None,
    compare_viewer: bool = False,
    viewer_filings: int | None = None,
    cache_dir: Path = EDGARTOOLS_CACHE_DIR,
) -> None:
    residuals = collect_residuals(tickers, periods, cache_dir)
    summary = summarize(residuals, tolerance)
    if compare_viewer:
        viewer = pd.concat(
            [
                collect_viewer_validations(ticker, period, viewer_filings, tolerance)
                for ticker in sorted(residuals["ticker"].unique())
                for period in periods
            ]
            or [pd.DataFrame(columns=list(VIEWER_COLUMNS))],
            ignore_index=True,
        )
        compared, viewer_only = compare_with_viewer(residuals, viewer, tolerance)
        summary = summary.merge(
            summarize_comparison(compared, viewer_only), on=_GROUP_KEYS, how="outer"
        )
        # Viewer-only groups (e.g. comprehensive income) have no counts of ours.
        counts = ["parents", "parent_periods", "non_zero"]
        summary[counts] = summary[counts].astype("Int64")
        details = flagged_residuals(compared, tolerance)
    else:
        details = non_zero_residuals(residuals, tolerance)
    logger.info("\n%s", _format_report(summary, details))
    if csv_path is not None:
        details.to_csv(csv_path, index=False)
        logger.info("Wrote %d residual rows to %s", len(details), csv_path)


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
        help="Also write the listed residuals to this CSV file.",
    )
    parser.add_argument(
        "--compare-viewer",
        action="store_true",
        help=(
            "Fetch filings from SEC and compare with edgartools' SEC-viewer "
            "calc validation (network; latest period of each filing only)."
        ),
    )
    parser.add_argument(
        "--viewer-filings",
        type=int,
        help=(
            "With --compare-viewer: newest filings to validate per ticker and "
            "period type. Default: as many as the cache holds (16 10-K / 64 10-Q)."
        ),
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
    run_report(
        args.ticker,
        periods,
        args.tolerance,
        args.csv,
        compare_viewer=args.compare_viewer,
        viewer_filings=args.viewer_filings,
    )


if __name__ == "__main__":
    main()
