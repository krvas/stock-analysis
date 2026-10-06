"""Unit tests for edgartools source (no live SEC requests)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import numpy as np
import pandas as pd
import pytest
from edgar.xbrl.exceptions import StatementNotFound

from src.api.edgartools import source
from src.api.edgartools.cache import (
    CachedPeriodBundle,
    StatementFrames,
    _load_index,
    is_period_bundle_stale,
    save_period_bundle,
    touch_company_cache,
)
from src.api.edgartools.source import (
    _align,
    _build_statement_dataframe,
    load_statement_set,
    setup_edgartools,
)
from src.config import MAX_CACHE_QUARTERS, MAX_CACHE_YEARS
from src.models.statement import (
    CALC_EDGE_COLUMNS,
    EDGARTOOLS_METADATA_COLUMNS,
    Statement,
    StatementSet,
)

_GETTERS = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cashflow": "cash_flow_statement",
}


@pytest.fixture(autouse=True)
def _isolated_edgartools_cache(monkeypatch, tmp_path) -> None:
    """Keep setup_edgartools (run by load_statement_set) off the real data/
    cache: our cache dir and edgartools' data dir point at tmp_path, and
    HTTP_MGR already caches there so it is not rebuilt."""
    monkeypatch.setenv("EDGAR_LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(source, "EDGARTOOLS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        source.edgar.httpclient,
        "HTTP_MGR",
        MagicMock(cache_dir=str(tmp_path / "_tcache")),
    )


def _filing_df(period_column: str, rows: list[dict]) -> pd.DataFrame:
    """A per-filing edgartools detailed frame: metadata + two period columns.

    A row's ``axes`` (list of ``(axis, member)``) makes it dimensional: like
    edgartools, the frame exposes only the first pair, while the matching
    ``get_raw_data`` item (kept in ``frame.attrs["raw"]``, with a structural
    axis item in front) carries all of them in ``dimension_metadata``. A
    row's ``raw_weight`` is that raw item's role-specific calc ``weight``
    (``weight`` is the frame's, which edgartools fills from facts).
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
                "weight": row.get("raw_weight"),
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


def _default_standard(frame: pd.DataFrame) -> pd.DataFrame:
    """What edgartools' ``view="standard"`` keeps when no member filter applies:
    every row except dimensional breakdowns."""
    if frame.empty:
        return frame
    drop = frame["dimension"].eq(True) & frame["is_breakdown"].eq(True)
    return frame.loc[~drop].reset_index(drop=True)


def _role(statement_type: str) -> str:
    return f"http://example.com/role/{statement_type}"


def _mock_xbrl(
    frames_by_statement: dict[str, pd.DataFrame],
    standard_by_statement: dict[str, pd.DataFrame | Exception] | None = None,
    calc_trees: dict[str, dict[str, tuple[str | None, float]]] | None = None,
) -> MagicMock:
    """A filing whose statements return the given frames.

    ``to_dataframe(view="standard")`` returns ``standard_by_statement``'s frame
    (or raises it, if an exception), defaulting to :func:`_default_standard`.
    ``calc_trees`` maps a statement type to its role's calc nodes
    (``{element_id: (parent, weight)}``, default empty); ``find_statement``
    resolves each statement's canonical type to that role.
    """
    xbrl = MagicMock()
    standard_by_statement = standard_by_statement or {}
    calc_trees = calc_trees or {}
    xbrl.find_statement.side_effect = lambda key: ([], _role(key), key)
    xbrl.calculation_trees = {
        _role(statement_type): SimpleNamespace(
            all_nodes={
                element_id: SimpleNamespace(parent=parent, weight=weight)
                for element_id, (parent, weight) in calc_trees.get(
                    statement_type, {}
                ).items()
            }
        )
        for statement_type in _GETTERS
    }
    for statement_type, getter in _GETTERS.items():
        statement = MagicMock()
        statement.canonical_type = statement_type
        frame = frames_by_statement.get(statement_type, pd.DataFrame())
        standard = standard_by_statement.get(statement_type, _default_standard(frame))

        def to_dataframe(*, view, presentation, frame=frame, standard=standard):
            if view != "standard":
                return frame
            if isinstance(standard, Exception):
                raise standard
            return standard

        statement.to_dataframe.side_effect = to_dataframe
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

    df = _build_statement_dataframe(xbrls, "cashflow", max_periods=16).frame

    mock_periods.assert_called_once_with(
        xbrls.xbrl_list, "CashFlowStatement", max_periods=16
    )
    for xbrl in (newest, older):
        xbrl.statements.cash_flow_statement.assert_called_once_with(view="detailed")
        assert _to_dataframe_mock(xbrl, "cashflow").call_args_list == [
            call(view="detailed", presentation=False),
            call(view="standard", presentation=False),
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

    df = _build_statement_dataframe(xbrls, "income", max_periods=16).frame

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

    df = _build_statement_dataframe(xbrls, "income", max_periods=16).frame

    assert df["row_id"].tolist() == ["Rev|A=M"]


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_takes_role_weight_from_raw_data(mock_periods: MagicMock) -> None:
    """edgartools' frame ``weight`` comes from the concept's first fact (maybe
    another role's calc tree); the aligned raw item's weight is this role's.
    Dimensional rows take their concept's role weight; rows without a raw
    weight keep the frame's. Raw data is fetched once per filing statement."""
    frame = _filing_df(
        "2024-09-28 (FY)",
        [
            {"concept": "OpCF", "value": 10.0, "weight": np.nan},
            {
                "concept": "Unrealized",
                "value": 3.0,
                "weight": 1.0,
                "raw_weight": -1.0,
                "parent_concept": "OpCF",
            },
            {
                "concept": "Unrealized",
                "axes": [("A", "M")],
                "value": 2.0,
                "weight": 1.0,
            },
            {
                "concept": "Other",
                "value": 13.0,
                "weight": 1.0,
                "parent_concept": "OpCF",
            },
        ],
    )
    xbrl = _mock_xbrl({"cashflow": frame})
    xbrls = MagicMock()
    xbrls.xbrl_list = [xbrl]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"},
        {"xbrl_index": 0, "end_date": "2023-09-30", "period_type": "duration"},
    ]

    df = _build_statement_dataframe(xbrls, "cashflow", max_periods=16).frame

    statement = xbrl.statements.cash_flow_statement.return_value
    statement.get_raw_data.assert_called_once_with(view="detailed")
    weights = dict(zip(df["row_id"], df["weight"], strict=True))
    assert pd.isna(weights.pop("OpCF"))
    assert weights == {"Unrealized": -1.0, "Unrealized|A=M": -1.0, "Other": 1.0}


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_keeps_frame_weight_when_raw_misaligned(
    mock_periods: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    frame = _filing_df(
        "2024-09-28 (FY)",
        [{"concept": "Rev", "value": 1.0, "weight": 1.0, "raw_weight": -1.0}],
    )
    frame.attrs["raw"] = [{"concept": "Other", "is_dimension": False, "weight": -1.0}]
    xbrls = MagicMock()
    xbrls.xbrl_list = [_mock_xbrl({"income": frame})]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"}
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16).frame

    assert df["weight"].tolist() == [1.0]
    assert "Could not align raw data" in caplog.text


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_weight_is_newest_non_nan_across_filings(
    mock_periods: MagicMock,
) -> None:
    """A newer filing listing a calc child without a weight must not blank the
    weight older filings give; every other column stays newest-filing."""
    filings = [
        ("2024-09-28", "Newest label", "credit", np.nan),
        ("2023-09-30", "Middle label", "debit", -1.0),
        ("2022-09-24", "Oldest label", "debit", 1.0),
    ]
    xbrls = MagicMock()
    xbrls.xbrl_list = [
        _mock_xbrl(
            {
                "cashflow": _filing_df(
                    f"{end} (FY)",
                    [
                        {"concept": "Invest", "value": 1.0},
                        {
                            "concept": "Acq",
                            "label": label,
                            "balance": balance,
                            "weight": weight,
                            "parent_concept": "Invest",
                            "value": 1.0,
                        },
                    ],
                )
            }
        )
        for end, label, balance, weight in filings
    ]
    mock_periods.return_value = [
        {"xbrl_index": index, "end_date": end, "period_type": "duration"}
        for index, (end, *_) in enumerate(filings)
    ]

    df = _build_statement_dataframe(xbrls, "cashflow", max_periods=16).frame

    acq = df.set_index("row_id").loc["Acq"]
    assert acq["weight"] == -1.0
    assert acq["label"] == "Newest label"
    assert acq["balance"] == "credit"


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_empty_when_no_periods(mock_periods: MagicMock) -> None:
    mock_periods.return_value = []
    df = _build_statement_dataframe(MagicMock(), "income", max_periods=16).frame
    statement = Statement(df, "income")
    assert statement.periods == []
    assert statement.project("summary").empty


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_10q_period_takes_the_ytd_column_matching_its_duration(
    mock_periods: MagicMock,
) -> None:
    """A 10-Q frame has a 3-month and a nine-month column ending on the same
    date (edgartools labels them ``<end> (Q3)`` and ``<end> (YTD)``). The
    period meta describes the nine-month span (start_date..end_date, 272
    days), so the stored value must come from the YTD column, not from
    whichever same-end-date column comes first (here the 3-month one)."""
    frame = _filing_df(
        "2026-09-30 (Q3)",
        [{"concept": "us-gaap_Revenues", "label": "Revenue", "value": 10.0}],
    )
    frame["2026-09-30 (YTD)"] = 30.0
    assert list(frame.columns).index("2026-09-30 (Q3)") < list(frame.columns).index(
        "2026-09-30 (YTD)"
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [_mock_xbrl({"income": frame})]
    mock_periods.return_value = [
        {
            "xbrl_index": 0,
            "start_date": "2026-01-01",
            "end_date": "2026-09-30",
            "duration_days": 272,
            "period_type": "duration",
        }
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=8).frame

    assert df.loc[0, "2026-09-30"] == 30.0


@pytest.mark.parametrize(
    ("column", "warns"), [("2026-09-30", True), ("2025-12-31", False)]
)
@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_warns_when_filing_has_no_column_for_its_period(
    mock_periods: MagicMock,
    column: str,
    warns: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    frame = _filing_df(
        column, [{"concept": "us-gaap_Revenues", "label": "Revenue", "value": 1.0}]
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [_mock_xbrl({"income": frame})]
    mock_periods.return_value = [
        {
            "xbrl_index": 0,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "duration_days": 364,
            "period_type": "duration",
        }
    ]
    # Parametrization: "2025-12-31" matches the period; "2026-09-30" does not.
    with caplog.at_level("WARNING", logger=source.logger.name):
        _build_statement_dataframe(xbrls, "income", max_periods=8)

    messages = [
        r.getMessage() for r in caplog.records if "matches period" in r.getMessage()
    ]
    if warns:
        assert len(messages) == 1
        assert "income" in messages[0]
        assert "2025-12-31" in messages[0]
        assert "filing 0" in messages[0]
    else:
        assert messages == []


# Old tree: ProfitLoss under NetIncomeLoss; new tree: pretax income directly.
_OLD_TREE = {
    "us-gaap_NetIncomeLoss": (None, 1.0),
    "us-gaap_ProfitLoss": ("us-gaap_NetIncomeLoss", 1.0),
    "us-gaap_MinorityInterest": ("us-gaap_NetIncomeLoss", -1.0),
}
_NEW_TREE = {
    "us-gaap_NetIncomeLoss": (None, 1.0),
    "us-gaap_IncomeBeforeTax": ("us-gaap_NetIncomeLoss", 1.0),
    "us-gaap_IncomeTaxExpenseBenefit": ("us-gaap_NetIncomeLoss", -1.0),
    # Calc-only concept (not presented on the statement): still an edge.
    "aapl_NotPresented": ("us-gaap_IncomeBeforeTax", 1.0),
}


def _edges(frame: pd.DataFrame, period: str) -> set[tuple[str, str, float]]:
    rows = frame[frame["period"] == period]
    return set(
        zip(rows["concept"], rows["parent_concept"], rows["weight"], strict=True)
    )


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_gives_each_period_its_own_filings_calc_tree(
    mock_periods: MagicMock,
) -> None:
    rows = [{"concept": "us-gaap_NetIncomeLoss", "value": 1.0}]
    newest = _mock_xbrl(
        {"income": _filing_df("2024-09-28 (FY)", rows)},
        calc_trees={"income": _NEW_TREE},
    )
    older = _mock_xbrl(
        {"income": _filing_df("2015-09-03 (FY)", rows)},
        calc_trees={"income": _OLD_TREE},
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [newest, older]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"},
        {"xbrl_index": 0, "end_date": "2023-09-30", "period_type": "duration"},
        {"xbrl_index": 1, "end_date": "2015-09-03", "period_type": "duration"},
    ]

    built = _build_statement_dataframe(xbrls, "income", max_periods=16)

    assert isinstance(built, StatementFrames)
    edges = built.calc_edges
    assert list(edges.columns) == list(CALC_EDGE_COLUMNS)
    new_edges = {
        ("us-gaap_IncomeBeforeTax", "us-gaap_NetIncomeLoss", 1.0),
        ("us-gaap_IncomeTaxExpenseBenefit", "us-gaap_NetIncomeLoss", -1.0),
        ("aapl_NotPresented", "us-gaap_IncomeBeforeTax", 1.0),
    }
    assert _edges(edges, "2024-09-28") == new_edges
    # A filing contributing two periods gives both its tree.
    assert _edges(edges, "2023-09-30") == new_edges
    assert _edges(edges, "2015-09-03") == {
        ("us-gaap_ProfitLoss", "us-gaap_NetIncomeLoss", 1.0),
        ("us-gaap_MinorityInterest", "us-gaap_NetIncomeLoss", -1.0),
    }
    for xbrl in (newest, older):
        xbrl.find_statement.assert_called_once_with("income")

    statement = Statement(built.frame, "income", calc_edges=edges)
    pd.testing.assert_frame_equal(statement.calc_edges, edges)


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_normalizes_colon_element_ids(mock_periods: MagicMock) -> None:
    tree = {
        "us-gaap:NetIncomeLoss": (None, 1.0),
        "us-gaap:ProfitLoss": ("us-gaap:NetIncomeLoss", 1.0),
        "us-gaap_Tax": ("us-gaap:NetIncomeLoss", -1.0),
    }
    xbrl = _mock_xbrl(
        {"income": _filing_df("2024-09-28 (FY)", [{"concept": "X", "value": 1.0}])},
        calc_trees={"income": tree},
    )
    xbrls = MagicMock()
    xbrls.xbrl_list = [xbrl]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"}
    ]

    edges = _build_statement_dataframe(xbrls, "income", max_periods=16).calc_edges

    assert _edges(edges, "2024-09-28") == {
        ("us-gaap_ProfitLoss", "us-gaap_NetIncomeLoss", 1.0),
        ("us-gaap_Tax", "us-gaap_NetIncomeLoss", -1.0),
    }


@pytest.mark.parametrize(
    "failure",
    [
        StatementNotFound("IncomeStatement", 0.0, []),
        "no-role",
        "no-tree",
    ],
    ids=["not-found", "no-role", "no-tree"],
)
@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_role_lookup_failure_gives_no_edges(
    mock_periods: MagicMock, failure: object, caplog: pytest.LogCaptureFixture
) -> None:
    xbrl = _mock_xbrl(
        {"income": _filing_df("2024-09-28 (FY)", [{"concept": "X", "value": 1.0}])},
        calc_trees={"income": _NEW_TREE},
    )
    if isinstance(failure, Exception):
        xbrl.find_statement.side_effect = failure
    elif failure == "no-role":
        xbrl.find_statement.side_effect = lambda key: ([], None, key)
    else:
        xbrl.calculation_trees = {}
    xbrls = MagicMock()
    xbrls.xbrl_list = [xbrl]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"}
    ]

    with caplog.at_level("WARNING", logger="src.api.edgartools.source"):
        built = _build_statement_dataframe(xbrls, "income", max_periods=16)

    assert built.calc_edges.empty
    assert list(built.calc_edges.columns) == list(CALC_EDGE_COLUMNS)
    assert built.frame["row_id"].tolist() == ["X"]
    assert any("calc" in r.getMessage().lower() for r in caplog.records)


def _rows(frame: pd.DataFrame, positions: list[int]) -> pd.DataFrame:
    return frame.iloc[positions].reset_index(drop=True)


@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_stores_in_standard_from_newest_filing(mock_periods: MagicMock) -> None:
    """``in_standard`` is membership in edgartools' own standard frame (matched
    onto the detailed rows in order); like other metadata it comes from the
    newest filing the row appears in."""
    product = ("srt:ProductOrServiceAxis", "us-gaap:ProductMember")
    iphone = ("srt:ProductOrServiceAxis", "aapl:IPhoneMember")
    newest_frame = _filing_df(
        "2024-09-28 (FY)",
        [
            {"concept": "Rev", "value": 100.0},
            {"concept": "Rev", "axes": [product], "value": 70.0},
            {"concept": "Rev", "axes": [iphone], "value": 50.0},
            {
                "concept": "Rev",
                "axes": [("Geo", "Us")],
                "is_breakdown": True,
                "value": 9.0,
            },
            {"concept": "Cost", "value": 40.0},
        ],
    )
    older_frame = _filing_df(
        "2023-09-30 (FY)",
        [
            {"concept": "Rev", "value": 90.0},
            {"concept": "Rev", "axes": [iphone], "value": 45.0},
            {"concept": "Old", "axes": [("X", "Y")], "value": 2.0},
        ],
    )
    # edgartools' standard view drops iPhone (member filter) and Geo
    # (breakdown) in the newest filing but keeps iPhone in the older one.
    newest = _mock_xbrl(
        {"income": newest_frame}, {"income": _rows(newest_frame, [0, 1, 4])}
    )
    older = _mock_xbrl({"income": older_frame}, {"income": _rows(older_frame, [0, 1])})
    xbrls = MagicMock()
    xbrls.xbrl_list = [newest, older]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"},
        {"xbrl_index": 1, "end_date": "2023-09-30", "period_type": "duration"},
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16).frame

    flags = dict(zip(df["row_id"], df["in_standard"], strict=True))
    assert flags == {
        "Rev": True,
        "Rev|ProductOrServiceAxis=us-gaap:ProductMember": True,
        "Rev|ProductOrServiceAxis=aapl:IPhoneMember": False,
        "Rev|Geo=Us": False,
        "Cost": True,
        "Old|X=Y": False,
    }
    standard = Statement(df, "income").project("standard")
    assert standard["row_id"].tolist() == [
        "Rev",
        "Rev|ProductOrServiceAxis=us-gaap:ProductMember",
        "Cost",
    ]


@pytest.mark.parametrize(
    "standard",
    [
        RuntimeError("edgartools failed"),
        pd.DataFrame(),
        "misaligned",
    ],
    ids=["raises", "empty", "misaligned"],
)
@patch("src.api.edgartools.source.determine_optimal_periods")
def test_build_in_standard_falls_back_to_default(
    mock_periods: MagicMock, standard: object
) -> None:
    """If edgartools' standard frame is unavailable or cannot be aligned, the
    flags are left unset and ``Statement`` fills its default
    (``not dimension or not is_breakdown``)."""
    frame = _filing_df(
        "2024-09-28 (FY)",
        [
            {"concept": "Rev", "value": 1.0},
            {"concept": "Rev", "axes": [("A", "M")], "value": 1.0},
            {"concept": "Rev", "axes": [("B", "N")], "is_breakdown": True},
        ],
    )
    if isinstance(standard, str):
        standard = _rows(frame, [0]).assign(concept="NotInDetailed")
    xbrls = MagicMock()
    xbrls.xbrl_list = [_mock_xbrl({"income": frame}, {"income": standard})]
    mock_periods.return_value = [
        {"xbrl_index": 0, "end_date": "2024-09-28", "period_type": "duration"}
    ]

    df = _build_statement_dataframe(xbrls, "income", max_periods=16).frame

    assert df["in_standard"].isna().all()
    assert Statement(df, "income").frame["in_standard"].tolist() == [True, True, False]


# --- _align -----------------------------------------------------------------


def _eq(a: object, b: object) -> bool:
    return a == b


def test_align_matches_ordered_subsequence_skipping_gaps() -> None:
    assert _align(["a", "c", "a"], ["a", "b", "c", "d", "a"], _eq) == [0, 2, 4]


def test_align_repeated_items_match_in_order() -> None:
    assert _align(["x", "x"], ["x", "y", "x"], _eq) == [0, 2]


def test_align_empty_sub_records() -> None:
    assert _align([], ["a"], _eq) == []


@pytest.mark.parametrize(
    ("sub", "sup"),
    [(["z"], ["a", "b"]), (["b", "a"], ["a", "b"]), (["a", "a"], ["a"])],
    ids=["missing", "out-of-order", "too-many"],
)
def test_align_returns_none_when_not_a_subsequence(
    sub: list[str], sup: list[str]
) -> None:
    assert _align(sub, sup, _eq) is None


# --- load_statement_set -----------------------------------------------------


def _patch_fetch(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_periods: MagicMock,
    xbrl: MagicMock,
    period_meta: dict,
    *,
    filing_dates: dict[str, str | None] | None = None,
) -> MagicMock:
    """Mock ``Company``; ``filing_dates`` maps form -> latest filing date
    (``None`` = no filings of that form). Every form defaults to 2024-11-01."""
    xbrls = MagicMock()
    xbrls.xbrl_list = [xbrl]
    mock_xbrls_cls.from_filings.return_value = xbrls
    company = MagicMock()
    company.cik = 320193
    filing_dates = filing_dates or {}
    filings_by_form: dict[str, MagicMock] = {}

    def get_filings(*, form: str, amendments: bool) -> MagicMock:
        if form not in filings_by_form:
            filings = MagicMock()
            latest = filing_dates.get(form, "2024-11-01")
            filings.end_date = latest
            filings.__iter__.return_value = iter([])
            filings.head.return_value = filings
            filings_by_form[form] = filings
        return filings_by_form[form]

    company.get_filings.side_effect = get_filings
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
@patch("src.api.edgartools.source.read_period_bundle")
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
    assert company.get_filings.call_args_list[0] == call(
        form=expected_form, amendments=False
    )
    company.get_filings(
        form=expected_form, amendments=False
    ).head.assert_called_once_with(expected_cap)
    assert all(c.kwargs["max_periods"] == expected_cap for c in mock_periods.mock_calls)
    for st in _GETTERS:
        assert _to_dataframe_mock(xbrl, st).call_args_list == [
            call(view="detailed", presentation=False),
            call(view="standard", presentation=False),
        ]

    mock_save_bundle.assert_called_once()
    save_kwargs = mock_save_bundle.call_args.kwargs
    assert save_kwargs["cik"] == 320193
    assert save_kwargs["period"] == period
    assert save_kwargs["latest_filing_date"] == date(2024, 11, 1)
    saved = save_kwargs["bundle"]
    assert set(saved) == {"income", "balance", "cashflow"}
    assert all(isinstance(frames, StatementFrames) for frames in saved.values())
    pd.testing.assert_frame_equal(
        saved[statement_type].calc_edges,
        statement_set.get(statement_type).calc_edges,
    )
    mock_touch_cache.assert_called_once()


FRESHNESS_CASES = [
    # (period, latest 10-K, latest 10-Q, stored freshness date, stale on
    # 2026-10-05); quarterly max age 3 months, annual 12.
    ("quarterly", "2026-08-20", "2026-05-01", date(2026, 8, 20), False),
    ("quarterly", "2025-08-20", "2026-05-01", date(2026, 5, 1), True),
    ("quarterly", None, "2026-05-01", date(2026, 5, 1), True),
    ("annual", "2025-08-20", "2026-09-01", date(2025, 8, 20), True),
    ("annual", "2026-08-20", "2026-05-01", date(2026, 8, 20), False),
]


@pytest.mark.parametrize(
    ("period", "latest_10k", "latest_10q", "expected", "stale"), FRESHNESS_CASES
)
@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.save_period_bundle")
@patch("src.api.edgartools.source.read_period_bundle")
@patch("src.api.edgartools.source.find_cached_cik")
@patch("src.api.edgartools.source.determine_optimal_periods")
@patch("src.api.edgartools.source.XBRLS")
@patch("src.api.edgartools.source.Company")
def test_load_statement_set_freshness_date_uses_10k_for_quarterly(
    mock_company_cls: MagicMock,
    mock_xbrls_cls: MagicMock,
    mock_periods: MagicMock,
    mock_find_cached_cik: MagicMock,
    mock_load_bundle: MagicMock,
    mock_save_bundle: MagicMock,
    mock_touch_cache: MagicMock,
    period: str,
    latest_10k: str | None,
    latest_10q: str,
    expected: date,
    stale: bool,
) -> None:
    """Quarterly bundles store the newer of the latest 10-K and 10-Q dates
    (a year-end 10-K replaces the Q4 10-Q); annual stores the latest 10-K."""
    mock_find_cached_cik.return_value = None
    mock_load_bundle.return_value = None
    period_meta = {"end_date": "2026-03-31", "period_type": "duration"}
    rows = [{"concept": "Revenue", "label": "Revenue", "value": 1.0}]
    xbrl = _mock_xbrl({st: _filing_df("2026-03-31 (Q)", rows) for st in _GETTERS})
    _patch_fetch(
        mock_company_cls,
        mock_xbrls_cls,
        mock_periods,
        xbrl,
        period_meta,
        filing_dates={"10-K": latest_10k, "10-Q": latest_10q},
    )

    load_statement_set("MU", period)

    stored = mock_save_bundle.call_args.kwargs["latest_filing_date"]
    assert stored == expected
    assert (
        is_period_bundle_stale(stored, period=period, reference=date(2026, 10, 5))
        is stale
    )


def _cached_bundle() -> dict[str, StatementFrames]:
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
    edges = pd.DataFrame(
        {
            "period": ["2024-09-28", "2022-09-24"],
            "concept": ["Capex", "Capex"],
            "parent_concept": ["Revenue", "Revenue"],
            "weight": [-1.0, 1.0],
        }
    )
    return {
        st: StatementFrames(Statement(raw, st).frame, edges)
        for st in ("income", "balance", "cashflow")
    }


@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
@patch("src.api.edgartools.source.touch_company_cache")
@patch("src.api.edgartools.source.save_period_bundle")
@patch("src.api.edgartools.source.read_period_bundle")
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
    mock_load_bundle.return_value = CachedPeriodBundle(
        _cached_bundle(), date(2024, 11, 1), stale=False
    )

    statement_set = load_statement_set("AAPL", "annual")

    assert statement_set.periods == ("2024-09-28", "2023-09-30", "2022-09-24")
    pd.testing.assert_frame_equal(
        statement_set.income.calc_edges, _cached_bundle()["income"].calc_edges
    )
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


# --- stale bundles: rebuilt only when SEC has a newer filing ----------------
# These use the real cache module on the autouse fixture's tmp_path cache dir.

_TODAY = datetime.now(UTC).date()
_STALE_DATE = date(_TODAY.year - 2, 1, 2)  # stale for annual and quarterly


def _seed_cache(cache_dir: Path, period: str, latest_filing_date: date) -> None:
    save_period_bundle(
        cik=320193,
        period=period,
        latest_filing_date=latest_filing_date,
        bundle=_cached_bundle(),
        cache_dir=cache_dir,
    )
    touch_company_cache(cik=320193, ticker="AAPL", cache_dir=cache_dir)


def _last_accessed(cache_dir: Path) -> str:
    return _load_index(cache_dir)["companies"]["320193"]["last_accessed"]


def _stored_filing_date(cache_dir: Path, period: str) -> str:
    meta = cache_dir / "companies" / "320193" / period / "meta.json"
    return json.loads(meta.read_text())["latest_filing_date"]


@pytest.fixture
def _sec(tmp_path):
    """Patch SEC access for load_statement_set; yields the mocks."""
    with (
        patch.dict(
            "os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"}
        ),
        patch.object(source, "Company") as company_cls,
        patch.object(source, "XBRLS") as xbrls_cls,
        patch.object(source, "determine_optimal_periods") as periods,
    ):
        yield SimpleNamespace(company=company_cls, xbrls=xbrls_cls, periods=periods)


def _patch_sec_filings(sec, filing_dates: dict[str, str | None]) -> MagicMock:
    rows = [{"concept": "Revenue", "label": "Revenue", "value": 1.0}]
    xbrl = _mock_xbrl({st: _filing_df("2026-03-31 (Q)", rows) for st in _GETTERS})
    return _patch_fetch(
        sec.company,
        sec.xbrls,
        sec.periods,
        xbrl,
        {"end_date": "2026-03-31", "period_type": "duration"},
        filing_dates=filing_dates,
    )


def test_fresh_bundle_makes_no_sec_calls(tmp_path, _sec) -> None:
    _seed_cache(tmp_path, "annual", _TODAY)

    statement_set = load_statement_set("AAPL", "annual")

    assert statement_set.periods == ("2024-09-28", "2023-09-30", "2022-09-24")
    _sec.company.assert_not_called()
    _sec.xbrls.from_filings.assert_not_called()


@pytest.mark.parametrize(
    ("period", "filing_dates"),
    [
        ("annual", {"10-K": _STALE_DATE.isoformat()}),
        # Freshness date is the latest 10-K, newer than the latest 10-Q.
        (
            "quarterly",
            {"10-K": _STALE_DATE.isoformat(), "10-Q": "2000-01-01"},
        ),
        ("quarterly", {"10-K": "2000-01-01", "10-Q": _STALE_DATE.isoformat()}),
    ],
)
def test_stale_bundle_without_newer_filing_is_served_from_cache(
    tmp_path, _sec, period: str, filing_dates: dict[str, str]
) -> None:
    _seed_cache(tmp_path, period, _STALE_DATE)
    before = _last_accessed(tmp_path)
    company = _patch_sec_filings(_sec, filing_dates)

    statement_set = load_statement_set("AAPL", period)

    assert statement_set.periods == ("2024-09-28", "2023-09-30", "2022-09-24")
    assert company.get_filings.call_args_list[0] == call(
        form=source.FORM_BY_PERIOD[period], amendments=False
    )
    _sec.xbrls.from_filings.assert_not_called()
    _sec.periods.assert_not_called()
    assert _stored_filing_date(tmp_path, period) == _STALE_DATE.isoformat()
    assert _last_accessed(tmp_path) > before


@pytest.mark.parametrize(
    ("period", "filing_dates", "expected"),
    [
        ("annual", {"10-K": "2026-09-01"}, "2026-09-01"),
        ("quarterly", {"10-K": "2000-01-01", "10-Q": "2026-08-01"}, "2026-08-01"),
        # A year-end 10-K is the newer filing for a quarterly bundle.
        (
            "quarterly",
            {"10-K": "2026-09-01", "10-Q": _STALE_DATE.isoformat()},
            "2026-09-01",
        ),
    ],
)
def test_stale_bundle_with_newer_filing_is_rebuilt(
    tmp_path, _sec, period: str, filing_dates: dict[str, str], expected: str
) -> None:
    _seed_cache(tmp_path, period, _STALE_DATE)
    _patch_sec_filings(_sec, filing_dates)

    statement_set = load_statement_set("AAPL", period)

    assert statement_set.periods == ("2026-03-31",)
    _sec.xbrls.from_filings.assert_called_once()
    assert _stored_filing_date(tmp_path, period) == expected


@pytest.mark.parametrize("damage", ["schema", "corrupt"])
def test_unusable_bundle_is_rebuilt_even_without_newer_filing(
    tmp_path, _sec, damage: str
) -> None:
    _seed_cache(tmp_path, "annual", _STALE_DATE)
    bundle_dir = tmp_path / "companies" / "320193" / "annual"
    if damage == "schema":
        meta_path = bundle_dir / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["schema_version"] = -1
        meta_path.write_text(json.dumps(meta))
    else:
        (bundle_dir / "income.parquet").write_bytes(b"not parquet")
    _patch_sec_filings(_sec, {"10-K": _STALE_DATE.isoformat()})

    statement_set = load_statement_set("AAPL", "annual")

    assert statement_set.periods == ("2026-03-31",)
    _sec.xbrls.from_filings.assert_called_once()
    assert _stored_filing_date(tmp_path, "annual") == _STALE_DATE.isoformat()


@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
def test_setup_edgartools_points_http_cache_at_app_cache_dir(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(source, "EDGARTOOLS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(source, "load_project_dotenv", lambda: None)
    http = source.edgar.httpclient
    import_time = MagicMock(
        cache_mode="FileCache", cache_dir=str(tmp_path / "home" / "_tcache")
    )
    monkeypatch.setattr(http, "HTTP_MGR", import_time)

    setup_edgartools()
    ours = http.HTTP_MGR
    try:
        assert ours is not import_time
        import_time.close.assert_called_once()
        assert ours.cache_mode == "FileCache"
        assert Path(ours.cache_dir).resolve() == (tmp_path / "_tcache").resolve()

        setup_edgartools()
        assert http.HTTP_MGR is ours
    finally:
        ours.close()


def _write_app_cache(cache_dir: Path, http_cache_bytes: int) -> list[Path]:
    """Write an edgartools HTTP cache entry plus our own cache files."""
    host = cache_dir / "_tcache" / "www.sec.gov"
    host.mkdir(parents=True)
    (host / "doc").write_bytes(b"x" * http_cache_bytes)
    (host / "doc.meta").write_bytes(b"{}")
    ours = [
        cache_dir / "companies" / "320193" / "annual.parquet",
        cache_dir / "company_lru.json",
    ]
    for path in ours:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ours")
    return ours


@patch.dict("os.environ", {"EDGAR_IDENTITY": "ScreenerApp/1.0 test@example.com"})
def test_setup_edgartools_clears_http_cache_over_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(source, "EDGARTOOLS_HTTP_CACHE_MAX_MB", 1)
    monkeypatch.setattr(source, "load_project_dotenv", lambda: None)
    ours = _write_app_cache(tmp_path, 1_100_000)

    setup_edgartools()

    tcache = tmp_path / "_tcache"
    assert not tcache.exists() or not any(p.is_file() for p in tcache.rglob("*"))
    assert all(path.read_bytes() == b"ours" for path in ours)


def test_clear_http_cache_if_over_keeps_cache_under_limit(tmp_path) -> None:
    ours = _write_app_cache(tmp_path, 400)

    source._clear_http_cache_if_over(max_bytes=1_000)

    assert (tmp_path / "_tcache" / "www.sec.gov" / "doc").stat().st_size == 400
    assert (tmp_path / "_tcache" / "www.sec.gov" / "doc.meta").exists()
    assert all(path.exists() for path in ours)


def test_clear_http_cache_if_over_uses_edgartools_clear_cache(monkeypatch) -> None:
    clear = MagicMock(
        side_effect=[
            {"files_deleted": 2, "bytes_freed": 501, "errors": 0},
            {"files_deleted": 2, "bytes_freed": 501, "errors": 0},
        ]
    )
    monkeypatch.setattr(source, "clear_cache", clear)

    source._clear_http_cache_if_over(max_bytes=500)

    assert clear.call_args_list == [call(dry_run=True), call(dry_run=False)]


# --- failure handling in load_statement_set ---------------------------------


def _bundle_meta(cache_dir: Path, period: str) -> Path:
    return cache_dir / "companies" / "320193" / period / "meta.json"


def test_empty_build_is_not_cached_and_raises(tmp_path, _sec) -> None:
    """When all three statements build empty (no periods), load_statement_set
    raises ValueError instead of returning an empty set, writes no bundle,
    and the next call retries the build rather than serving an empty cache."""
    period = "annual"
    company = _patch_sec_filings(_sec, {"10-K": "2026-09-01"})
    _sec.periods.return_value = []

    with pytest.raises(ValueError):
        load_statement_set("AAPL", period)

    assert not _bundle_meta(tmp_path, period).exists()
    assert (
        source.read_period_bundle(cik=company.cik, period=period, cache_dir=tmp_path)
        is None
    )

    with pytest.raises(ValueError):
        load_statement_set("AAPL", period)
    assert _sec.xbrls.from_filings.call_count == 2


def test_stale_bundle_is_served_when_sec_is_unreachable(
    tmp_path, _sec, caplog: pytest.LogCaptureFixture
) -> None:
    """With a stale but readable bundle cached and SEC unreachable
    (``Company`` raises ConnectionError), load_statement_set logs a warning
    and returns the stale bundle's StatementSet; with a cold cache the error
    still propagates."""
    _sec.company.side_effect = ConnectionError("SEC unreachable")
    with pytest.raises(ConnectionError):
        load_statement_set("MSFT", "annual")  # cold cache: nothing to serve

    _seed_cache(tmp_path, "annual", _STALE_DATE)
    with caplog.at_level("WARNING", logger=source.logger.name):
        statement_set = load_statement_set("AAPL", "annual")

    assert statement_set.periods == ("2024-09-28", "2023-09-30", "2022-09-24")
    assert any(r.levelname == "WARNING" for r in caplog.records)
    _sec.xbrls.from_filings.assert_not_called()
