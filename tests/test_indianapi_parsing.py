"""Unit tests for IndianAPI parsing helpers (no live API calls)."""

from __future__ import annotations

from datetime import date

from src.utils.indianapi_parsing import (
    coalesce,
    map_fields,
    parse_action_date,
    parse_amount,
    parse_dividend_amount,
    parse_ratio,
    period_metadata,
    rows_to_dict,
)

SAMPLE_PERIOD = {
    "EndDate": "2025-03-31",
    "FiscalYear": "2025",
    "StatementDate": "2026-03-31",
    "Type": "Annual",
    "fiscalPeriodNumber": 0,
    "stockFinancialMap": {
        "INC": [
            {"key": "TotalRevenue", "value": "54969.49", "displayName": "Revenue"},
            {"key": "NetIncome", "value": "-100.50", "displayName": "Net Income"},
            {"key": "periodType", "value": "Months", "displayName": "period Type"},
            {"key": "DilutedEPSExcludingExtraOrdItems", "value": "31.13", "displayName": "EPS"},
        ],
    },
}


class TestParseAmount:
    def test_parses_decimals_and_negatives(self) -> None:
        assert parse_amount("54969.49", "TotalRevenue") == 54969.49
        assert parse_amount("-100.50", "NetIncome") == -100.50

    def test_skips_metadata_keys(self) -> None:
        assert parse_amount("Months", "periodType") is None
        assert parse_amount("12", "periodLength") is None

    def test_treats_empty_and_dash_as_missing(self) -> None:
        assert parse_amount("", "TotalRevenue") is None
        assert parse_amount("-", "TotalRevenue") is None
        assert parse_amount(None, "TotalRevenue") is None


class TestRowsToDict:
    def test_skips_period_metadata_keys(self) -> None:
        rows = SAMPLE_PERIOD["stockFinancialMap"]["INC"]
        parsed = rows_to_dict(rows)
        assert "periodType" not in parsed
        assert parsed["TotalRevenue"] == 54969.49
        assert parsed["NetIncome"] == -100.50

    def test_empty_rows_returns_empty_dict(self) -> None:
        assert rows_to_dict(None) == {}
        assert rows_to_dict([]) == {}


class TestCoalesce:
    def test_returns_first_non_null(self) -> None:
        row = {"A": None, "B": 1.5, "C": 2.0}
        assert coalesce(row, "A", "B", "C") == 1.5
        assert coalesce(row, "A", "C", "B") == 2.0

    def test_returns_none_when_all_missing(self) -> None:
        assert coalesce({"A": None}, "A", "B") is None


class TestMapFields:
    def test_maps_columns_via_coalesce(self) -> None:
        row = rows_to_dict(SAMPLE_PERIOD["stockFinancialMap"]["INC"])
        mapped = map_fields(
            row,
            {
                "revenue": ("TotalRevenue", "Revenue"),
                "net_profit": ("NetIncome",),
                "eps_diluted": ("DilutedEPSExcludingExtraOrdItems",),
            },
        )
        assert mapped["revenue"] == 54969.49
        assert mapped["net_profit"] == -100.50
        assert mapped["eps_diluted"] == 31.13


class TestPeriodMetadata:
    def test_annual_period(self) -> None:
        meta = period_metadata(SAMPLE_PERIOD)
        assert meta["period_end_date"] == date(2025, 3, 31)
        assert meta["period_type"] == "annual"
        assert meta["fiscal_year"] == 2025
        assert meta["fiscal_quarter"] is None
        assert meta["currency"] == "INR"

    def test_quarterly_period(self) -> None:
        interim = {**SAMPLE_PERIOD, "Type": "Interim", "EndDate": "2025-06-30"}
        meta = period_metadata(interim)
        assert meta["period_type"] == "quarterly"
        assert meta["fiscal_quarter"] == 1


class TestCorporateActionParsing:
    def test_parse_action_date(self) -> None:
        assert parse_action_date("05-06-2026") == date(2026, 6, 5)
        assert parse_action_date("2025-03-31") == date(2025, 3, 31)
        assert parse_action_date("invalid") is None

    def test_parse_ratio(self) -> None:
        assert parse_ratio("1:1") == (1, 1)
        assert parse_ratio("bad") == (None, None)

    def test_parse_dividend_amount(self) -> None:
        text = "recommended a dividend of Rs.6.00 per equity share"
        assert parse_dividend_amount(text) == 6.0
