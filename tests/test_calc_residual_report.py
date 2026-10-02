"""Tests for the calc-residual report CLI helpers (edgartools is faked)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pandas as pd
import pytest

from src.api.edgartools.cache import save_period_bundle, touch_company_cache
from src.models.statement import Statement
from src.pipelines import calc_residual_report as report
from src.pipelines.calc_residual_report import (
    COMPARE_COLUMNS,
    collect_residuals,
    collect_viewer_validations,
    compare_with_viewer,
    flagged_residuals,
    non_zero_residuals,
    summarize,
    summarize_comparison,
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
    assert (details["n_nan_weight_children"] == 0).all()
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
            "n_nan_weight_children": [0, 1, 0],
        }
    )
    details = non_zero_residuals(residuals, tolerance=0.5)

    assert details["row_id"].tolist() == ["b", "a"]
    assert details["n_nan_weight_children"].tolist() == [1, 0]


INCOME_ROLE = "CONSOLIDATED STATEMENTS OF OPERATIONS"


class _Viewer:
    """Fake ``FilingViewer``: values in thousands (display units)."""

    def __init__(self, results: list[tuple[str, str, float, float]]) -> None:
        self.financial_statements = [
            SimpleNamespace(short_name=INCOME_ROLE, currency_scaling=1000),
            SimpleNamespace(short_name="BALANCE SHEETS", currency_scaling=1000),
        ]
        self._results = results

    def validate(self, tolerance: float = 0.5) -> list[dict]:
        return [
            {
                "parent": SimpleNamespace(id=concept),
                "role": role,
                "expected": expected,
                "computed": computed,
                "difference": expected - computed,
                "valid": abs(expected - computed) <= tolerance,
            }
            for concept, role, expected, computed in self._results
        ]


# ticker -> newest-first filings (period_of_report, viewer or None).
FILINGS = {
    "AAA": [
        # P1 matches ours (4 − 4 = 0); "Extra" is viewer-only.
        (
            P1,
            _Viewer(
                [
                    ("Total", INCOME_ROLE, 0.004, 0.004),
                    ("Extra", "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME", 1, 1),
                ]
            ),
        ),
        (P2, None),  # no MetaLinks.json: skipped, P2 is ours-only
    ],
    "BBB": [
        (P1, None),
        # Ours: 13 − 3 = 10; the viewer says 0 → disagree.
        (P2, _Viewer([("Total", INCOME_ROLE, 0.003, 0.003)])),
    ],
}


class _Filings(list):
    def head(self, n: int) -> _Filings:
        return _Filings(self[:n])


class _Company:
    calls: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker

    def get_filings(self, form: str, amendments: bool) -> _Filings:
        assert amendments is False
        _Company.calls.append((self.ticker, form))
        return _Filings(
            SimpleNamespace(form=form, period_of_report=period, viewer=viewer)
            for period, viewer in FILINGS[self.ticker.upper()]
        )


@pytest.fixture
def fake_edgar(monkeypatch: pytest.MonkeyPatch) -> type[_Company]:
    _Company.calls = []
    monkeypatch.setattr(report, "Company", _Company)
    monkeypatch.setattr(report, "setup_edgartools", lambda: None)
    return _Company


def _viewer_frame() -> pd.DataFrame:
    return pd.concat(
        [collect_viewer_validations(t, "annual") for t in ("AAA", "BBB")],
        ignore_index=True,
    )


def test_collect_viewer_validations_scales_and_maps(fake_edgar) -> None:
    viewer = collect_viewer_validations("aaa", "annual", max_filings=5)

    assert fake_edgar.calls == [("aaa", "10-K")]
    # The P2 filing has no viewer and is skipped.
    assert viewer["period"].tolist() == [P1, P1]
    assert viewer["ticker"].tolist() == ["AAA", "AAA"]
    assert viewer["statement"].tolist() == [
        "income",
        "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME",
    ]
    # Display units (thousands) scaled back to raw units.
    assert viewer["viewer_expected"].tolist() == pytest.approx([4.0, 1.0])
    assert viewer["viewer_valid"].tolist() == [True, True]


def test_viewer_statement_mapping() -> None:
    assert report._viewer_statement("CONSOLIDATED BALANCE SHEETS") == "balance"
    assert report._viewer_statement("Consolidated Statements of Cash Flows") == (
        "cashflow"
    )
    assert report._viewer_statement("STATEMENTS OF INCOME") == "income"
    assert report._viewer_statement(
        "STATEMENTS OF OPERATIONS AND COMPREHENSIVE LOSS"
    ) == ("income")
    assert report._viewer_statement("STATEMENTS OF COMPREHENSIVE INCOME") == (
        "STATEMENTS OF COMPREHENSIVE INCOME"
    )
    assert report._viewer_statement("BALANCE SHEETS (Parenthetical)") == (
        "BALANCE SHEETS (Parenthetical)"
    )


def test_compare_with_viewer(tmp_path: Path, fake_edgar) -> None:
    residuals = collect_residuals(None, ("annual",), _cache(tmp_path))
    compared, viewer_only = compare_with_viewer(residuals, _viewer_frame(), 0.5)

    assert len(compared) == len(residuals)
    income = compared[compared["statement"] == "income"].set_index(["ticker", "period"])
    # Match + agree.
    assert income.loc[("AAA", P1), "agrees"] is True
    assert income.loc[("AAA", P1), "viewer_valid"]
    # Match + disagree.
    assert income.loc[("BBB", P2), "residual"] == 10.0
    assert income.loc[("BBB", P2), "agrees"] is False
    # Ours only (no viewer for that filing).
    assert income.loc[("AAA", P2), "agrees"] is None
    assert pd.isna(income.loc[("AAA", P2), "viewer_difference"])
    # Viewer only.
    assert viewer_only["concept"].tolist() == ["Extra"]

    summary = summarize_comparison(compared, viewer_only).set_index(
        ["ticker", "statement"]
    )
    assert summary.loc[("AAA", "income")].to_dict() == {
        "period_type": "annual",
        "matched": 1,
        "agree": 1,
        "ours_only": 1,
        "viewer_only": 0,
    }
    assert summary.loc[("BBB", "income"), "agree"] == 0
    assert summary.loc[("BBB", "balance"), "matched"] == 0
    comprehensive = "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME"
    assert summary.loc[("AAA", comprehensive), "viewer_only"] == 1

    flagged = flagged_residuals(compared, 0.5)
    assert list(flagged.columns[-len(COMPARE_COLUMNS) :]) == list(COMPARE_COLUMNS)
    # BBB's non-zero residuals (all statements); BBB income also disagrees.
    assert set(flagged["ticker"]) == {"BBB"}
    assert len(flagged) == 3


def test_run_report_compare_viewer_writes_viewer_columns(
    tmp_path: Path, fake_edgar
) -> None:
    csv_path = tmp_path / "out.csv"
    report.run_report(
        None, ("annual",), 0.5, csv_path, True, cache_dir=_cache(tmp_path)
    )

    details = pd.read_csv(csv_path)
    assert set(COMPARE_COLUMNS) <= set(details.columns)
    assert {call[0] for call in fake_edgar.calls} == {"AAA", "BBB"}


def test_run_report_default_does_not_touch_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access in a cache-only run")

    monkeypatch.setattr(report, "Company", fail)
    monkeypatch.setattr(report, "setup_edgartools", fail)
    csv_path = tmp_path / "out.csv"
    report.run_report(None, ("annual",), 0.5, csv_path, cache_dir=_cache(tmp_path))

    details = pd.read_csv(csv_path)
    assert "viewer_difference" not in details.columns
    assert len(details) == 3
