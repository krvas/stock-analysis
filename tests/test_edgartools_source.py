"""Unit tests for edgartools source (no live SEC requests)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.api.edgartools.source import get_statement_views

STATEMENT_CASES = [
    ("income", "annual", "income_statement", {"end_date": "2024-09-28", "period_type": "duration"}),
    ("income", "quarterly", "income_statement", {"end_date": "2024-06-29", "period_type": "duration"}),
    ("balance", "annual", "balance_sheet", {"date": "2024-09-28", "period_type": "instant"}),
    ("balance", "quarterly", "balance_sheet", {"date": "2024-06-29", "period_type": "instant"}),
    ("cashflow", "annual", "cash_flow_statement", {"end_date": "2024-09-28", "period_type": "duration"}),
    ("cashflow", "quarterly", "cash_flow_statement", {"end_date": "2024-06-29", "period_type": "duration"}),
]


def _period_column_name(period_meta: dict) -> str:
    period_date = period_meta.get("end_date") or period_meta["date"]
    suffix = " (Q)" if period_meta.get("period_type") == "duration" and "06" in str(period_date) else " (FY)"
    return f"{period_date}{suffix}"


def _make_filing_df(period_meta: dict) -> pd.DataFrame:
    column = _period_column_name(period_meta)
    return pd.DataFrame(
        {
            "label": ["Total assets", "Total liabilities"],
            "concept": ["Assets", "Liabilities"],
            "standard_concept": ["Assets", "Liabilities"],
            column: [100.0, 40.0],
            "level": [0, 0],
            "abstract": [False, False],
        }
    )


def _make_period_meta(period_meta: dict) -> dict:
    return {
        "xbrl_index": 0,
        "period_key": "test_period",
        **period_meta,
    }


@pytest.mark.parametrize(
    ("statement_type", "period", "getter_name", "period_meta"),
    STATEMENT_CASES,
    ids=[f"{st}-{p}" for st, p, _, _ in STATEMENT_CASES],
)
@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.save_period_bundle")
@patch("src.api.edgartools.source.load_period_bundle")
@patch("src.api.edgartools.source.find_cached_cik")
@patch("src.api.edgartools.source.determine_optimal_periods")
@patch("src.api.edgartools.source.XBRLS")
@patch("src.api.edgartools.source.Company")
def test_get_statement_views_all_statement_and_period_types(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_determine_periods: MagicMock,
    mock_find_cached_cik: MagicMock,
    mock_load_bundle: MagicMock,
    mock_save_bundle: MagicMock,
    mock_touch_cache: MagicMock,
    statement_type: str,
    period: str,
    getter_name: str,
    period_meta: dict,
) -> None:
    mock_find_cached_cik.return_value = None
    mock_load_bundle.return_value = None

    filing_df = _make_filing_df(period_meta)
    mock_statement = MagicMock()
    mock_statement.to_dataframe.return_value = filing_df

    mock_statements = MagicMock()
    for getter in ("income_statement", "balance_sheet", "cash_flow_statement"):
        getattr(mock_statements, getter).return_value = mock_statement

    mock_xbrl = MagicMock()
    mock_xbrl.statements = mock_statements

    mock_xbrls = MagicMock()
    mock_xbrls.xbrl_list = [mock_xbrl]
    mock_xbrls_cls.from_filings.return_value = mock_xbrls

    mock_company = MagicMock()
    mock_company.cik = 320193
    mock_filings = MagicMock()
    mock_filings.end_date = "2024-11-01"
    mock_company.get_filings.return_value.head.return_value = mock_filings
    mock_company_cls.return_value = mock_company

    mock_determine_periods.return_value = [_make_period_meta(period_meta)]

    views = get_statement_views("AAPL", statement_type, period, num_periods=1)

    assert set(views) == {"summary", "standard", "detailed"}
    expected_period = str(period_meta.get("end_date") or period_meta["date"])
    for name, frame in views.items():
        assert isinstance(frame, pd.DataFrame), name
        assert not frame.empty, name
        assert expected_period in frame.columns, name
        assert "level" in frame.columns

    expected_form = "10-K" if period == "annual" else "10-Q"
    mock_company.get_filings.assert_called_once_with(form=expected_form, amendments=False)
    mock_save_bundle.assert_called_once()
    save_kwargs = mock_save_bundle.call_args.kwargs
    assert save_kwargs["latest_filing_date"] == date(2024, 11, 1)
    assert set(save_kwargs["views"]) == {"income", "balance", "cashflow"}
    mock_touch_cache.assert_called_once()
    assert getattr(mock_statements, getter_name).call_count == 3
    assert mock_statement.to_dataframe.call_count == 9


@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.load_period_bundle")
@patch("src.api.edgartools.source.find_cached_cik")
@patch("src.api.edgartools.source.Company")
def test_get_statement_views_returns_cached_without_sec_fetch(
    mock_company_cls: MagicMock,
    mock_find_cached_cik: MagicMock,
    mock_load_bundle: MagicMock,
    mock_touch_cache: MagicMock,
) -> None:
    cached_views = {
        "summary": pd.DataFrame({"label": ["Revenue"], "2024-09-28": [100.0]}),
        "standard": pd.DataFrame({"label": ["Revenue"], "2024-09-28": [100.0]}),
        "detailed": pd.DataFrame({"label": ["Revenue"], "2024-09-28": [100.0]}),
    }
    mock_find_cached_cik.return_value = "320193"
    mock_load_bundle.return_value = {
        "income": cached_views,
        "balance": cached_views,
        "cashflow": cached_views,
    }

    views = get_statement_views("AAPL", "income", "annual", num_periods=10)

    assert views is cached_views
    mock_company_cls.assert_not_called()
    mock_touch_cache.assert_called_once_with(
        cik="320193",
        ticker="AAPL",
        cache_dir=mock_touch_cache.call_args.kwargs["cache_dir"],
        max_companies=mock_touch_cache.call_args.kwargs["max_companies"],
    )


@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.save_period_bundle")
@patch("src.api.edgartools.source.load_period_bundle")
@patch("src.api.edgartools.source.find_cached_cik")
@patch("src.api.edgartools.source.Company")
def test_get_statement_views_reuses_bundle_for_other_statement_type(
    mock_company_cls: MagicMock,
    mock_find_cached_cik: MagicMock,
    mock_load_bundle: MagicMock,
    mock_save_bundle: MagicMock,
    mock_touch_cache: MagicMock,
) -> None:
    balance_views = {
        "summary": pd.DataFrame({"label": ["Assets"], "2024-09-28": [100.0]}),
        "standard": pd.DataFrame({"label": ["Assets"], "2024-09-28": [100.0]}),
        "detailed": pd.DataFrame({"label": ["Assets"], "2024-09-28": [100.0]}),
    }
    mock_find_cached_cik.return_value = "320193"
    mock_load_bundle.return_value = {
        "income": balance_views,
        "balance": balance_views,
        "cashflow": balance_views,
    }

    views = get_statement_views("AAPL", "balance", "annual", num_periods=10)

    assert views is balance_views
    mock_company_cls.assert_not_called()
    mock_save_bundle.assert_not_called()
