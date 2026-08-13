"""Unit tests for edgartools source (no live SEC requests)."""

from __future__ import annotations

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
@patch("src.api.edgartools.source.determine_optimal_periods")
@patch("src.api.edgartools.source.XBRLS")
@patch("src.api.edgartools.source.Company")
def test_get_statement_views_all_statement_and_period_types(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_determine_periods: MagicMock,
    statement_type: str,
    period: str,
    getter_name: str,
    period_meta: dict,
) -> None:
    filing_df = _make_filing_df(period_meta)
    mock_statement = MagicMock()
    mock_statement.to_dataframe.return_value = filing_df

    mock_statements = MagicMock()
    getattr(mock_statements, getter_name).return_value = mock_statement

    mock_xbrl = MagicMock()
    mock_xbrl.statements = mock_statements

    mock_xbrls = MagicMock()
    mock_xbrls.xbrl_list = [mock_xbrl]
    mock_xbrls_cls.from_filings.return_value = mock_xbrls

    mock_company = MagicMock()
    mock_filings = MagicMock()
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
    assert getattr(mock_statements, getter_name).call_count == 3
    assert mock_statement.to_dataframe.call_count == 3
