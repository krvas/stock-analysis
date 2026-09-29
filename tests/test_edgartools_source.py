"""Unit tests for edgartools source (no live SEC requests)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, call, patch

import numpy as np
import pandas as pd
import pytest

from src.api.edgartools.source import (
    _build_statement_dataframe,
    load_statement_set,
)
from src.config import MAX_CACHE_QUARTERS, MAX_CACHE_YEARS
from src.models.statement import EDGARTOOLS_METADATA_COLUMNS, Statement, StatementSet

_GETTERS = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cashflow": "cash_flow_statement",
}


def _filing_df(period_column: str, rows: list[dict]) -> pd.DataFrame:
    """A per-filing edgartools detailed frame: metadata + two period columns.

    A row's ``axes`` (list of ``(axis, member)``) makes it dimensional: like
    edgartools, the frame exposes only the first pair, while the matching
    ``get_raw_data`` item (kept in ``frame.attrs["raw"]``, with a structural
    axis item in front) carries all of them in ``dimension_metadata``.
    """
    records = []
    raw: list[dict] = [{"concept": "us-gaap_StatementTable", "label": "[Table]"}]
    for row in rows:
        axes = row.get("axes") or []
        if axes:
            row = {
                **row,
                "dimension": True,
                "dimension_axis": axes[0][0],
                "dimension_member": axes[0][1],
            }
        raw.append(
            {
                "concept": row["concept"],
                "is_dimension": bool(row.get("dimension", False)),
                "full_dimension_label": None,
                "dimension_metadata": [
                    {"dimension": axis, "member": member} for axis, member in axes
                ]
                or (
                    [
                        {
                            "dimension": row["dimension_axis"],
                            "member": row["dimension_member"],
                        }
                    ]
                    if row.get("dimension")
                    else []
                ),
            }
        )
        record = {
            "concept": row["concept"],
            "label": row.get("label", row["concept"]),
            "standard_concept": row.get("standard_concept"),
            period_column: row.get("value"),
            "2000-01-01 (FY)": 1.0,  # another period in the filing; never used
            "level": row.get("level", 1),
            "abstract": row.get("abstract", False),
            "dimension": row.get("dimension", False),
            "is_breakdown": row.get("is_breakdown", False),
            "dimension_axis": row.get("dimension_axis"),
            "dimension_member": row.get("dimension_member"),
            "dimension_member_label": None,
            "dimension_label": None,
            "balance": row.get("balance"),
            "weight": row.get("weight", np.nan),
            "preferred_sign": row.get("preferred_sign", np.nan),
            "parent_concept": row.get("parent_concept"),
            "parent_abstract_concept": None,
            "unit": "usd",
            "point_in_time": False,
        }
        records.append(record)
    frame = pd.DataFrame(records)
    frame.attrs["raw"] = raw
    return frame


def _mock_xbrl(
    frames_by_statement: dict[str, pd.DataFrame],
    valid_members: dict[str, set[str]] | None = None,
) -> MagicMock:
    """A filing whose statements return the given frames.

    ``valid_members`` is what edgartools' ``_get_valid_dimensional_members``
    returns for the statement's presentation tree (axis -> members).
    """
    xbrl = MagicMock()
    xbrl.find_statement.return_value = ([], "role", "Statement")
    xbrl.presentation_trees = {"role": "tree"}
    xbrl._get_valid_dimensional_members.return_value = valid_members or {}
    for statement_type, getter in _GETTERS.items():
        statement = MagicMock()
        statement.canonical_type = statement_type
        frame = frames_by_statement.get(statement_type, pd.DataFrame())
        statement.to_dataframe.return_value = frame
        statement.get_raw_data.return_value = frame.attrs.get("raw", [])
        getattr(xbrl.statements, getter).return_value = statement
    return xbrl


def _to_dataframe_mock(xbrl: MagicMock, statement_type: str) -> MagicMock:
    return getattr(xbrl.statements, _GETTERS[statement_type]).return_value.to_dataframe


# --- _build_statement_dataframe ---------------------------------------------


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_one_raw_frame_with_newest_metadata(mock_periods: MagicMock) -> None:
    newest = _mock_xbrl(
        {
            "cashflow": _filing_df(
                "2024-09-28 (FY)",
                [
                    {"concept": "Cash", "label": "Cash, beginning", "value": 10.0},
                    {
                        "concept": "Capex",
                        "label": "Payments for PP&E",
                        "value": 5.0,
                        "preferred_sign": -1.0,
                        "balance": "credit",
                    },
                    {
                        "concept": "Rev",
                        "label": "iPhone",
                        "value": 7.0,
                        "dimension": True,
                        "is_breakdown": True,
                        "dimension_axis": "Axis",
                        "dimension_member": "IphoneMember",
                    },
                    {"concept": "Cash", "label": "Cash, ending", "value": 20.0},
                ],
            )
        }
    )
    older = _mock_xbrl(
        {
            "cashflow": _filing_df(
                "2023-09-30 (FY)",
                [
                    {"concept": "Cash", "label": "Cash at start", "value": 8.0},
                    {
                        "concept": "Capex",
                        "label": "Old capex label",
                        "value": 4.0,
                        "balance": "debit",
                    },
                    {"concept": "OldOnly", "label": "Discontinued", "value": 3.0},
                    {"concept": "Cash", "label": "Cash at end", "value": 10.0},
                ],
            )
        }
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [newest, older]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"},
        {"xbrl_index": 1, "end_date": "2023-09-30", "period_type": "duration"},
    ]

    df = _build_statement_dataframe(xbrls, "cashflow", max_periods=16)

    mock_periods.assert_called_once_with(
        xbrls.xbrl_list, "CashFlowStatement", max_periods=16
    )
    for xbrl in (newest, older):
        xbrl.statements.cash_flow_statement.assert_called_once_with(view="detailed")
        assert _to_dataframe_mock(xbrl, "cashflow").call_args_list == [
            call(view="detailed", presentation=False)
        ]
        # Other statements are not touched while building cashflow.
        _to_dataframe_mock(xbrl, "income").assert_not_called()

    assert list(df.columns) == [
        "row_id",
        *EDGARTOOLS_METADATA_COLUMNS,
        "dimension_key",
        "in_standard",
        "2024-09-28",
        "2023-09-30",
    ]
    assert df["row_id"].tolist() == [
        "Cash",
        "Capex",
        "Rev|Axis=IphoneMember",
        "Cash#2",
        "OldOnly",
    ]
    by_id = df.set_index("row_id")
    # Metadata from the newest filing the row appears in.
    assert by_id.loc["Capex", "label"] == "Payments for PP&E"
    assert by_id.loc["Capex", "balance"] == "credit"
    assert by_id.loc["Capex", "preferred_sign"] == -1.0
    assert by_id.loc["Cash#2", "label"] == "Cash, ending"
    assert by_id.loc["OldOnly", "label"] == "Discontinued"
    assert bool(by_id.loc["Rev|Axis=IphoneMember", "is_breakdown"])
    # Raw signs, occurrence-matched values across filings.
    assert by_id.loc["Capex"].loc[["2024-09-28", "2023-09-30"]].tolist() == [5.0, 4.0]
    assert by_id.loc["Cash"].loc[["2024-09-28", "2023-09-30"]].tolist() == [10.0, 8.0]
    assert by_id.loc["Cash#2"].loc[["2024-09-28", "2023-09-30"]].tolist() == [
        20.0,
        10.0,
    ]
    assert pd.isna(by_id.loc["OldOnly", "2024-09-28"])

    statement = Statement(df, "cashflow")
    assert statement.periods == ["2024-09-28", "2023-09-30"]


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_keys_multi_axis_rows_by_every_axis(mock_periods: MagicMock) -> None:
    """Rows sharing a primary axis/member but differing in a secondary member
    stay distinct and merge by full dimension even when the older filing
    presents them in a different order (and with a renamed axis namespace)."""
    seg = ("srt:ConsolidationItemsAxis", "us-gaap_OperatingSegmentsMember")
    newest = _mock_xbrl(
        {
            "income": _filing_df(
                "2024-09-28 (FY)",
                [
                    {"concept": "Rev", "value": 100.0},
                    {
                        "concept": "Rev",
                        "label": "Americas",
                        "axes": [seg, ("us-gaap:SegmentsAxis", "AmericasMember")],
                        "value": 60.0,
                    },
                    {
                        "concept": "Rev",
                        "label": "Europe",
                        "axes": [seg, ("us-gaap:SegmentsAxis", "EuropeMember")],
                        "value": 40.0,
                    },
                ],
            )
        }
    )
    old_seg = ("us-gaap:ConsolidationItemsAxis", "us-gaap_OperatingSegmentsMember")
    older = _mock_xbrl(
        {
            "income": _filing_df(
                "2023-09-30 (FY)",
                [
                    {"concept": "Rev", "value": 90.0},
                    {
                        "concept": "Rev",
                        "label": "Total segments",
                        "axes": [old_seg],
                        "value": 90.0,
                    },
                    {
                        "concept": "Rev",
                        "label": "Europe",
                        "axes": [old_seg, ("us-gaap:SegmentsAxis", "EuropeMember")],
                        "value": 35.0,
                    },
                    {
                        "concept": "Rev",
                        "label": "Americas",
                        "axes": [old_seg, ("us-gaap:SegmentsAxis", "AmericasMember")],
                        "value": 55.0,
                    },
                ],
            )
        }
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [newest, older]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"},
        {"xbrl_index": 1, "end_date": "2023-09-30", "period_type": "duration"},
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16)

    segment = "ConsolidationItemsAxis=us-gaap_OperatingSegmentsMember"
    americas = f"Rev|{segment}|SegmentsAxis=AmericasMember"
    europe = f"Rev|{segment}|SegmentsAxis=EuropeMember"
    assert df["row_id"].tolist() == ["Rev", americas, europe, f"Rev|{segment}"]
    by_id = df.set_index("row_id")
    periods = ["2024-09-28", "2023-09-30"]
    assert by_id.loc[americas, periods].tolist() == [60.0, 55.0]
    assert by_id.loc[europe, periods].tolist() == [40.0, 35.0]
    assert pd.isna(by_id.loc[f"Rev|{segment}", "2024-09-28"])
    assert by_id.loc[f"Rev|{segment}", "2023-09-30"] == 90.0
    assert by_id.loc[americas, "dimension_key"] == (
        "srt:ConsolidationItemsAxis=us-gaap_OperatingSegmentsMember"
        "|us-gaap:SegmentsAxis=AmericasMember"
    )
    assert pd.isna(by_id.loc["Rev", "dimension_key"])
    Statement(df, "income")  # unique row ids


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_falls_back_to_primary_dimension_when_raw_misaligned(
    mock_periods: MagicMock,
) -> None:
    frame = _filing_df(
        "2024-09-28 (FY)",
        [{"concept": "Rev", "axes": [("A", "M"), ("B", "N")], "value": 1.0}],
    )
    frame.attrs["raw"] = [{"concept": "Other", "is_dimension": False}]
    xbrls = MagicMock()
    xbrls.xbrl_list = [_mock_xbrl({"income": frame})]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"}
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16)

    assert df["row_id"].tolist() == ["Rev|A=M"]


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_empty_when_no_periods(mock_periods: MagicMock) -> None:
    mock_periods.return_value = []
    df = _build_statement_dataframe(MagicMock(), "income", max_periods=16)
    statement = Statement(df, "income")
    assert statement.periods == []
    assert statement.project("summary").empty


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_stores_in_standard_from_newest_filing(mock_periods: MagicMock) -> None:
    """``in_standard`` replicates edgartools' standard view: non-dimensional
    rows are in; dimensional rows need ``not is_breakdown`` and every axis's
    member listed in the presentation tree (axes not listed never exclude).
    Like other metadata it comes from the newest filing the row appears in."""
    product = ("srt:ProductOrServiceAxis", "us-gaap:ProductMember")
    iphone = ("srt:ProductOrServiceAxis", "aapl:IPhoneMember")
    ppe = ("us-gaap:PropertyPlantAndEquipmentByTypeAxis", "us-gaap:LandMember")
    newest = _mock_xbrl(
        {
            "income": _filing_df(
                "2024-09-28 (FY)",
                [
                    {"concept": "Rev", "value": 100.0},
                    {"concept": "Rev", "axes": [product], "value": 70.0},
                    {"concept": "Rev", "axes": [iphone], "value": 50.0},
                    {"concept": "Rev", "axes": [ppe], "value": 1.0},
                    {
                        "concept": "Rev",
                        "axes": [("Geo", "Us")],
                        "is_breakdown": True,
                        "value": 9.0,
                    },
                ],
            )
        },
        valid_members={"srt_ProductOrServiceAxis": {"us-gaap_ProductMember"}},
    )
    older = _mock_xbrl(
        {
            "income": _filing_df(
                "2023-09-30 (FY)",
                [
                    {"concept": "Rev", "value": 90.0},
                    # Valid in the older filing, but the newest filing wins.
                    {"concept": "Rev", "axes": [iphone], "value": 45.0},
                    {"concept": "Old", "axes": [("X", "Y")], "value": 2.0},
                ],
            )
        },
        valid_members={"srt_ProductOrServiceAxis": {"aapl_IPhoneMember"}},
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [newest, older]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"},
        {"xbrl_index": 1, "end_date": "2023-09-30", "period_type": "duration"},
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16)

    newest.find_statement.assert_called_once_with("income")
    newest._get_valid_dimensional_members.assert_called_once_with("tree")
    # Still exactly one to_dataframe call per filing.
    assert _to_dataframe_mock(newest, "income").call_count == 1
    flags = dict(zip(df["row_id"], df["in_standard"], strict=True))
    assert flags == {
        "Rev": True,
        "Rev|ProductOrServiceAxis=us-gaap:ProductMember": True,
        "Rev|ProductOrServiceAxis=aapl:IPhoneMember": False,
        "Rev|PropertyPlantAndEquipmentByTypeAxis=us-gaap:LandMember": True,
        "Rev|Geo=Us": False,
        "Old|X=Y": True,
    }

    standard = Statement(df, "income").project("standard")
    assert standard["row_id"].tolist() == [
        "Rev",
        "Rev|ProductOrServiceAxis=us-gaap:ProductMember",
        "Rev|PropertyPlantAndEquipmentByTypeAxis=us-gaap:LandMember",
        "Old|X=Y",
    ]


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_in_standard_unfiltered_when_tree_unresolved(
    mock_periods: MagicMock,
) -> None:
    xbrl = _mock_xbrl(
        {
            "income": _filing_df(
                "2024-09-28 (FY)",
                [{"concept": "Rev", "axes": [("A", "M")], "value": 1.0}],
            )
        },
        valid_members={"A": {"Other"}},
    )
    xbrl.find_statement.return_value = ([], None, None)
    xbrls = MagicMock()
    xbrls.xbrl_list = [xbrl]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"}
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16)

    assert df["in_standard"].tolist() == [True]
    xbrl._get_valid_dimensional_members.assert_not_called()


# --- load_statement_set -----------------------------------------------------


def _patch_fetch(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_periods: MagicMock,
    xbrl: MagicMock,
    period_meta: dict,
) -> MagicMock:
    xbrls = MagicMock()
    xbrls.xbrl_list = [xbrl]
    mock_xbrls_cls.from_filings.return_value = xbrls
    company = MagicMock()
    company.cik = 320193
    filings = MagicMock()
    filings.end_date = "2024-11-01"
    company.get_filings.return_value.head.return_value = filings
    mock_company_cls.return_value = company
    mock_periods.return_value = [{"xbrl_index": 0, **period_meta}]
    return company


STATEMENT_CASES = [
    ("income", "annual", {"end_date": "2024-09-28", "period_type": "duration"}),
    ("income", "quarterly", {"end_date": "2024-06-29", "period_type": "duration"}),
    ("balance", "annual", {"date": "2024-09-28", "period_type": "instant"}),
    ("balance", "quarterly", {"date": "2024-06-29", "period_type": "instant"}),
    ("cashflow", "annual", {"end_date": "2024-09-28", "period_type": "duration"}),
    ("cashflow", "quarterly", {"end_date": "2024-06-29", "period_type": "duration"}),
]


@pytest.mark.parametrize(
    ("statement_type", "period", "period_meta"),
    STATEMENT_CASES,
    ids=[f"{st}-{p}" for st, p, _ in STATEMENT_CASES],
)
@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.save_period_bundle")
@patch("src.api.edgartools.source.load_period_bundle")
@patch("src.api.edgartools.source.find_cached_cik")
@patch("src.api.edgartools.source.determine_optimal_periods")
@patch("src.api.edgartools.source.XBRLS")
@patch("src.api.edgartools.source.Company")
def test_load_statement_set_fetches_builds_and_saves(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_periods: MagicMock,
    mock_find_cached_cik: MagicMock,
    mock_load_bundle: MagicMock,
    mock_save_bundle: MagicMock,
    mock_touch_cache: MagicMock,
    statement_type: str,
    period: str,
    period_meta: dict,
) -> None:
    mock_find_cached_cik.return_value = None
    mock_load_bundle.return_value = None
    period_date = period_meta.get("end_date") or period_meta["date"]
    rows = [
        {"concept": "Assets", "label": "Total assets", "value": 100.0},
        {"concept": "Liabilities", "label": "Total liabilities", "value": 40.0},
    ]
    xbrl = _mock_xbrl({st: _filing_df(f"{period_date} (FY)", rows) for st in _GETTERS})
    company = _patch_fetch(
        mock_company_cls, mock_xbrls_cls, mock_periods, xbrl, period_meta
    )

    statement_set = load_statement_set("AAPL", period)

    assert isinstance(statement_set, StatementSet)
    assert statement_set.periods == (period_date,)
    frame = statement_set.get(statement_type).frame
    assert frame["row_id"].tolist() == ["Assets", "Liabilities"]
    assert frame["is_total"].tolist() == [True, True]
    assert "unit" not in frame.columns and "point_in_time" not in frame.columns

    expected_form = "10-K" if period == "annual" else "10-Q"
    expected_cap = MAX_CACHE_YEARS if period == "annual" else MAX_CACHE_QUARTERS
    company.get_filings.assert_called_once_with(form=expected_form, amendments=False)
    company.get_filings.return_value.head.assert_called_once_with(expected_cap)
    assert all(c.kwargs["max_periods"] == expected_cap for c in mock_periods.mock_calls)
    for st in _GETTERS:
        _to_dataframe_mock(xbrl, st).assert_called_once_with(
            view="detailed", presentation=False
        )

    mock_save_bundle.assert_called_once()
    save_kwargs = mock_save_bundle.call_args.kwargs
    assert save_kwargs["cik"] == 320193
    assert save_kwargs["period"] == period
    assert save_kwargs["latest_filing_date"] == date(2024, 11, 1)
    assert set(save_kwargs["frames"]) == {"income", "balance", "cashflow"}
    assert tuple(save_kwargs["periods"]) == (period_date,)
    mock_touch_cache.assert_called_once()


def _cached_bundle() -> dict[str, pd.DataFrame]:
    raw = pd.DataFrame(
        {
            "concept": ["Revenue", "Capex", "Rev"],
            "label": ["Revenue", "Capex", "iPhone"],
            "standard_concept": ["Revenue", "Capex", "Revenue"],
            "level": [0, 0, 1],
            "abstract": [False, False, False],
            "dimension": [False, False, True],
            "is_breakdown": [False, False, True],
            "dimension_axis": [None, None, "Axis"],
            "dimension_member": [None, None, "IphoneMember"],
            "preferred_sign": [np.nan, -1.0, np.nan],
            "2024-09-28": [100.0, 5.0, 60.0],
            "2023-09-30": [90.0, 4.0, 50.0],
            "2022-09-24": [80.0, 3.0, 40.0],
        }
    )
    return {st: Statement(raw, st).frame for st in ("income", "balance", "cashflow")}


@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.save_period_bundle")
@patch("src.api.edgartools.source.load_period_bundle")
@patch("src.api.edgartools.source.find_cached_cik")
@patch("src.api.edgartools.source.Company")
def test_load_statement_set_returns_cached_without_sec_fetch(
    mock_company_cls: MagicMock,
    mock_find_cached_cik: MagicMock,
    mock_load_bundle: MagicMock,
    mock_save_bundle: MagicMock,
    mock_touch_cache: MagicMock,
) -> None:
    mock_find_cached_cik.return_value = "320193"
    mock_load_bundle.return_value = _cached_bundle()

    statement_set = load_statement_set("AAPL", "annual")

    assert statement_set.periods == ("2024-09-28", "2023-09-30", "2022-09-24")
    mock_load_bundle.assert_called_once_with(
        cik="320193",
        period="annual",
        cache_dir=mock_load_bundle.call_args.kwargs["cache_dir"],
    )
    mock_company_cls.assert_not_called()
    mock_save_bundle.assert_not_called()
    mock_touch_cache.assert_called_once_with(
        cik="320193",
        ticker="AAPL",
        cache_dir=mock_touch_cache.call_args.kwargs["cache_dir"],
        max_companies=mock_touch_cache.call_args.kwargs["max_companies"],
    )
