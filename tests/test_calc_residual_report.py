"""Tests for the calc-residual report CLI helpers (cache reads only)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.api.edgartools.cache import save_period_bundle, touch_company_cache
from src.models.statement import Statement
from src.pipelines.calc_residual_report import (
    collect_residuals,
    non_zero_residuals,
    summarize,
)

P1, P2 = "2024-12-31", "2023-12-31"


def _frame(total_p2: float) -> pd.DataFrame:
    raw = pd.DataFrame(
        {
            "concept": ["Total", "A", "B"],
            "label": ["Total", "A", "B"],
            "dimension": [False, False, False],
            "weight": [None, 1.0, -1.0],
            "parent_concept": [None, "Total", "Total"],
            P1: [4.0, 10.0, 6.0],
            P2: [total_p2, 8.0, 5.0],
        }
    )
    return Statement(raw, "income").frame


def _cache(tmp_path: Path) -> Path:
    cache_dir = tmp_path / "edgartools_cache"
    today = datetime.now(UTC).date()
    for cik, ticker, total_p2 in ((1, "AAA", 3.0), (2, "BBB", 13.0)):
        save_period_bundle(
            cik=cik,
            period="annual",
            latest_filing_date=today,
            frames={st: _frame(total_p2) for st in ("income", "balance", "cashflow")},
            cache_dir=cache_dir,
        )
        touch_company_cache(cik=cik, ticker=ticker, cache_dir=cache_dir)
    return cache_dir


def test_collect_summarize_and_list_non_zero(tmp_path: Path) -> None:
    cache_dir = _cache(tmp_path)
    residuals = collect_residuals(None, ("annual", "quarterly"), cache_dir)

    # Quarterly bundles are missing and skipped.
    assert set(residuals["period_type"]) == {"annual"}
    assert set(residuals["ticker"]) == {"AAA", "BBB"}

    summary = summarize(residuals, tolerance=0.5).set_index(["ticker", "statement"])
    assert summary.loc[("AAA", "income"), "parent_periods"] == 2
    assert summary.loc[("AAA", "income"), "zero_share"] == 1.0
    assert summary.loc[("BBB", "income"), "non_zero"] == 1
    assert summary.loc[("BBB", "income"), "zero_share"] == 0.5

    details = non_zero_residuals(residuals, tolerance=0.5)
    assert set(details["ticker"]) == {"BBB"}
    assert details["residual"].tolist() == [10.0, 10.0, 10.0]
    assert set(details["period"]) == {P2}


def test_collect_only_requested_tickers(tmp_path: Path) -> None:
    cache_dir = _cache(tmp_path)
    residuals = collect_residuals(["aaa", "ZZZ"], ("annual",), cache_dir)

    assert set(residuals["ticker"]) == {"AAA"}


def test_non_zero_sorted_by_abs_relative(tmp_path: Path) -> None:
    residuals = pd.DataFrame(
        {
            "ticker": ["T"] * 3,
            "period_type": ["annual"] * 3,
            "statement": ["income"] * 3,
            "row_id": ["a", "b", "c"],
            "label": ["a", "b", "c"],
            "period": [P1] * 3,
            "reported": [100.0, 10.0, 0.0],
            "computed": [90.0, 15.0, 0.0],
            "residual": [10.0, -5.0, 0.0],
            "relative": [0.1, -0.5, float("nan")],
            "n_children": [1, 1, 1],
            "n_nan_children": [0, 0, 0],
        }
    )
    details = non_zero_residuals(residuals, tolerance=0.5)

    assert details["row_id"].tolist() == ["b", "a"]
