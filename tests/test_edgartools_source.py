"""Unit tests for edgartools source (no live SEC requests)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from src.api.edgartools.source import get_statement_views


def _make_filing_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "label": ["Revenue", "Net income"],
            "concept": ["Revenue", "NetIncome"],
            "standard_concept": ["Revenue", "NetIncome"],
            "2024-09-28 (FY)": [100.0, 25.0],
            "level": [1, 0],
            "abstract": [False, False],
        }
    )


@patch("src.api.edgartools.source.set_identity")
@patch("src.api.edgartools.source.determine_optimal_periods")
@patch("src.api.edgartools.source.XBRLS")
@patch("src.api.edgartools.source.Company")
def test_get_statement_views_returns_three_non_empty_views(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_determine_periods: MagicMock,
    mock_set_identity: MagicMock,
) -> None:
    filing_df = _make_filing_df()
    mock_statement = MagicMock()
    mock_statement.to_dataframe.return_value = filing_df

    mock_xbrl = MagicMock()
    mock_xbrl.statements.income_statement.return_value = mock_statement

    mock_xbrls = MagicMock()
    mock_xbrls.xbrl_list = [mock_xbrl]
    mock_xbrls_cls.from_filings.return_value = mock_xbrls

    mock_company = MagicMock()
    mock_filings = MagicMock()
    mock_company.get_filings.return_value.head.return_value = mock_filings
    mock_company_cls.return_value = mock_company

    mock_determine_periods.return_value = [
        {
            "xbrl_index": 0,
            "end_date": "2024-09-28",
            "period_key": "duration_2023-09-30_2024-09-28",
        }
    ]

    views = get_statement_views("AAPL", "income", "annual", num_periods=1)

    assert set(views) == {"summary", "standard", "detailed"}
    for name, frame in views.items():
        assert isinstance(frame, pd.DataFrame)
        assert not frame.empty, f"{name} view should not be empty"
        assert "level" in frame.columns
        assert "is_total" in frame.columns
        assert "2024-09-28" in frame.columns

    assert mock_xbrls_cls.from_filings.call_args.kwargs["filter_amendments"] is True
    assert mock_xbrl.statements.income_statement.call_count == 3
    assert mock_statement.to_dataframe.call_count == 3
    mock_set_identity.assert_called_once()
