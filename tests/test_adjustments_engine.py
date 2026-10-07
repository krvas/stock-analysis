"""Adjustments engine: pure helpers plus invariants on the data-test tickers."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments, ordered_specs
from src.adjustments.specs import from_prefs
from src.adjustments.types.opex_to_capex import schedule
from src.adjustments.types.owner_earnings import owner_earnings
from src.api.edgartools.source import load_statement_set
from src.config import load_project_dotenv
from tests.test_edgar_data import TICKERS_FILE, _test_tickers

CASH_CHANGE = (
    "us-gaap_CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
    "PeriodIncreaseDecreaseIncludingExchangeRateEffect"
)


def test_schedule_straight_line_same_year_start() -> None:
    amort, net = schedule({"2022": 30.0, "2023": 30.0, "2024": 30.0}, life=3)
    assert amort == {"2022": 10.0, "2023": 20.0, "2024": 30.0}
    assert net == pytest.approx({"2022": 20.0, "2023": 30.0, "2024": 30.0})


def test_owner_earnings_formula() -> None:
    parts = pd.DataFrame({"pretax": [100.0], "da": [20.0], "nwc": [-10.0]})
    out = owner_earnings(parts, da_pct=50, nwc_pct=100)
    # 100 + 20 - 10 - 10 - (-10)
    assert out["owner_earnings"].iloc[0] == pytest.approx(110.0)


def test_ordered_specs_until_stops_before_type() -> None:
    specs = [AdjustmentSpec("owner_earnings", {}), AdjustmentSpec("opex_to_capex", {})]
    assert [s.type_id for s in ordered_specs(specs)] == [
        "opex_to_capex",
        "owner_earnings",
    ]
    assert [s.type_id for s in ordered_specs(specs, until="owner_earnings")] == [
        "opex_to_capex"
    ]


def test_from_prefs_groups_by_type() -> None:
    prefs = pd.DataFrame(
        {
            "adjustment_type": ["owner_earnings", "opex_to_capex", "owner_earnings"],
            "base_concept": ["maintenance_da", "us-gaap_R", "maintenance_nwc"],
            "value": [60.0, 5.0, 50.0],
        }
    )
    specs = from_prefs(prefs)
    assert [s.type_id for s in specs] == ["opex_to_capex", "owner_earnings"]
    assert specs[0].params == {"rows": {"us-gaap_R": 5.0}}
    assert specs[1].params == {"maintenance_da": 60.0, "maintenance_nwc": 50.0}


def _value(ss, statement: str, concept: str, period: str) -> float:
    frame = ss.get(statement).frame
    rows = frame[(frame["concept"] == concept) & ~frame["dimension"].eq(True)]
    return float(rows[period].iloc[0])


@pytest.mark.data
def test_engine_invariants_on_test_tickers() -> None:
    load_project_dotenv()
    if not os.environ.get("EDGAR_IDENTITY") or not TICKERS_FILE.exists():
        pytest.skip("data test prerequisites missing")
    for ticker in _test_tickers():
        base = load_statement_set(ticker, "annual")
        unchanged = apply_adjustments(base, [])
        for st in ("income", "balance", "cashflow"):
            periods = base.get(st).periods
            a = base.get(st).frame[periods].apply(pd.to_numeric, errors="coerce")
            b = unchanged.get(st).frame[periods].apply(pd.to_numeric, errors="coerce")
            assert np.allclose(a.fillna(0), b.fillna(0)), (ticker, st)

        opex = base.income.find(standard_concept="ResearchAndDevelopmentExpenses")
        if opex.empty:
            continue
        spec = AdjustmentSpec("opex_to_capex", {"rows": {opex["row_id"].iloc[0]: 5}})
        adjusted = apply_adjustments(base, [spec])
        period = base.income.periods[0]
        assert _value(adjusted, "balance", "us-gaap_Assets", period) == pytest.approx(
            _value(
                adjusted, "balance", "us-gaap_LiabilitiesAndStockholdersEquity", period
            )
        ), ticker
        assert _value(adjusted, "income", "us-gaap_NetIncomeLoss", period) == (
            pytest.approx(_value(adjusted, "cashflow", "us-gaap_NetIncomeLoss", period))
        ), ticker
        if CASH_CHANGE in set(base.cashflow.frame["concept"]):
            assert _value(adjusted, "cashflow", CASH_CHANGE, period) == pytest.approx(
                _value(base, "cashflow", CASH_CHANGE, period)
            ), ticker
