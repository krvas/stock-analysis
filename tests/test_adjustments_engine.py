"""Adjustments engine: pure helpers plus invariants on the data-test tickers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.adjustments.base import AdjustmentSpec
from src.adjustments.engine import apply_adjustments, ordered_specs
from src.adjustments.specs import from_prefs
from src.adjustments.types import owner_earnings as oe
from src.adjustments.types.opex_to_capex import schedule
from src.api.edgartools.source import load_statement_set
from src.api.edgartools.standard_terms import (
    ASSET_PARENTS,
    CFI,
    CFO,
    DA_COMPONENT_AXIS,
    EQUITY_PARENTS,
    PRETAX_INCOME,
)
from src.models.statement import bool_flag

CASH_CHANGE = (
    "us-gaap_CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
    "PeriodIncreaseDecreaseIncludingExchangeRateEffect"
)


def test_schedule_straight_line_same_year_start() -> None:
    amort, net = schedule({"2022": 30.0, "2023": 30.0, "2024": 30.0}, life=3)
    assert amort == {"2022": 10.0, "2023": 20.0, "2024": 30.0}
    assert net == pytest.approx({"2022": 20.0, "2023": 30.0, "2024": 30.0})


def test_owner_earnings_formula_with_per_item_maintenance() -> None:
    items = pd.DataFrame(
        {"row_id": ["dep", "amort"], "label": ["Dep", "Amort"], "2024": [15.0, 5.0]}
    )
    maintenance = oe.maintenance_da(items, {"dep": 60, "amort": 20})
    assert maintenance["2024"] == pytest.approx(10.0)
    parts = pd.DataFrame(
        {"pretax": [100.0], "da": [20.0], "nwc": [-10.0]}, index=["2024"]
    )
    out = oe.owner_earnings(parts, maintenance, nwc_pct=100)
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
    assert [s.type_id for s in specs] == [
        "opex_to_capex",
        "owner_earnings",
        "assets_in_use",
    ]
    assert specs[0].params == {"rows": {"us-gaap_R": 5.0}}
    assert specs[1].params == {"maintenance_da": 60.0, "maintenance_nwc": 50.0}


def _row_values(ss, statement: str, concept: str) -> pd.Series | None:
    frame = ss.get(statement).frame
    rows = frame[(frame["concept"] == concept) & ~frame["dimension"].eq(True)]
    if rows.empty:
        return None
    return pd.to_numeric(rows.iloc[0][ss.get(statement).periods], errors="coerce")


# R&D first; SG&A stands in for a filer without R&D, so every ticker
# exercises opex_to_capex.
CAPITALIZABLE = ("ResearchAndDevelopmentExpenses", "SellingGeneralAndAdminExpenses")


def _capitalizable_row(income) -> pd.Series:
    for standard_concept in CAPITALIZABLE:
        rows = income.find(standard_concept=standard_concept)
        if not rows.empty:
            return rows.iloc[0]
    pytest.skip(f"no {' or '.join(CAPITALIZABLE)} row to capitalize")


@pytest.mark.data
def test_no_specs_reproduce_reported_statements(data_ticker: str) -> None:
    base = load_statement_set(data_ticker, "annual")
    run = apply_adjustments(base, [])
    assert run.applied == () and run.skipped == ()
    for st in ("income", "balance", "cashflow"):
        periods = base.get(st).periods
        a = base.get(st).frame[periods].apply(pd.to_numeric, errors="coerce")
        b = run.statements.get(st).frame[periods].apply(pd.to_numeric, errors="coerce")
        assert np.allclose(a.fillna(0), b.fillna(0)), (data_ticker, st)


@pytest.mark.data
def test_capitalized_opex_moves_every_period_by_its_schedule(data_ticker: str) -> None:
    base = load_statement_set(data_ticker, "annual")
    row = _capitalizable_row(base.income)
    life = 5
    spec = AdjustmentSpec("opex_to_capex", {"rows": {row["row_id"]: life}})
    run = apply_adjustments(base, [spec])
    assert run.applied == (spec,) and run.skipped == (), data_ticker
    adjusted = run.statements

    spend = {
        p: float(row[p]) for p in base.income.periods if pd.notna(pd.to_numeric(row[p]))
    }
    _, net = schedule(spend, life)
    balance_concepts = set(base.balance.frame["concept"])
    equity = next(c for c in EQUITY_PARENTS if c in balance_concepts)
    expected = {
        ("balance", "us-gaap_Assets"): net,
        ("balance", equity): net,
        ("balance", "us-gaap_LiabilitiesAndStockholdersEquity"): net,
        ("cashflow", CFO): spend,
        ("cashflow", CFI): {p: -v for p, v in spend.items()},
    }
    for (st, concept), change in expected.items():
        before = _row_values(base, st, concept)
        after = _row_values(adjusted, st, concept)
        assert before is not None, (data_ticker, concept)
        checked = [p for p in change if p in before.index and pd.notna(before[p])]
        assert checked, (data_ticker, concept, "no reported period to compare")
        for period in checked:
            assert after[period] - before[period] == pytest.approx(change[period]), (
                data_ticker,
                concept,
                period,
            )

    local = str(row["concept"]).split("_", 1)[-1]
    income_edges = base.income.calc_edges
    expense_parent = set(
        income_edges.loc[income_edges["concept"] == row["concept"], "parent_concept"]
    )
    inserted = {
        ("income", f"adj_Amortization{local}"): expense_parent,
        ("balance", f"adj_Capitalized{local}"): set(ASSET_PARENTS),
        ("balance", f"adj_EquityCapitalized{local}"): set(EQUITY_PARENTS),
        ("cashflow", f"adj_Amortization{local}"): {CFO},
        ("cashflow", f"adj_Capitalized{local}"): {CFI},
    }
    for (st, concept), parents in inserted.items():
        statement = adjusted.get(st)
        assert concept in set(statement.frame["row_id"]), (data_ticker, concept)
        reported = [_row_values(base, st, parent) for parent in parents]
        expected_periods = {
            p
            for p in spend
            if any(v is not None and pd.notna(v.get(p)) for v in reported)
        }
        assert expected_periods, (data_ticker, concept, "no period with a parent")
        edges = statement.calc_edges
        wired = set(edges.loc[edges["concept"] == concept, "period"])
        assert expected_periods <= wired, (data_ticker, concept)

    for period in base.balance.periods:
        assets = _row_values(adjusted, "balance", "us-gaap_Assets")[period]
        total = _row_values(
            adjusted, "balance", "us-gaap_LiabilitiesAndStockholdersEquity"
        )[period]
        if pd.notna(assets) and pd.notna(total):
            assert assets == pytest.approx(total), (data_ticker, period)
    income_ni = _row_values(adjusted, "income", "us-gaap_NetIncomeLoss")
    cash_ni = _row_values(adjusted, "cashflow", "us-gaap_NetIncomeLoss")
    for period in cash_ni.index:
        if period in income_ni.index and pd.notna(income_ni[period]):
            assert cash_ni[period] == pytest.approx(income_ni[period]), (
                data_ticker,
                period,
            )
    if CASH_CHANGE in set(base.cashflow.frame["concept"]):
        assert np.allclose(
            _row_values(adjusted, "cashflow", CASH_CHANGE).fillna(0),
            _row_values(base, "cashflow", CASH_CHANGE).fillna(0),
        ), data_ticker


@pytest.mark.data
def test_da_breakdown_rows_sum_to_da_line(data_ticker: str) -> None:
    cashflow = load_statement_set(data_ticker, "annual").cashflow
    frame = cashflow.frame
    parts = frame[frame["dimension_axis"].eq(DA_COMPONENT_AXIS)]
    if parts.empty:
        return
    line = frame[frame["row_id"] == parts["concept"].iloc[0]].iloc[0]
    assert (
        parts["row_id"].str.startswith(f"{line['concept']}|{DA_COMPONENT_AXIS}=").all()
    ), data_ticker
    assert not parts["in_standard"].any(), data_ticker
    for period in cashflow.periods:
        values = pd.to_numeric(parts[period], errors="coerce")
        if values.notna().any() and pd.notna(line[period]):
            assert values.sum() == pytest.approx(line[period]), (data_ticker, period)
    da = _cfo_depreciation(cashflow)
    items = oe.da_items(cashflow)
    for period in da.dropna().index:
        assert items[period].sum() == pytest.approx(da[period]), (data_ticker, period)


def _cfo_children(cashflow, prefix: str) -> pd.Series:
    edges = cashflow.calc_edges
    local = edges["concept"].str.split("_").str[-1]
    parent = edges["parent_concept"].fillna("").str.split("_").str[-1]
    edges = edges[
        local.str.startswith(prefix) & parent.str.startswith(CFO.split("_")[-1])
    ]
    frame = cashflow.frame
    values = frame[~bool_flag(frame, "dimension")].drop_duplicates("concept")
    values = values.set_index("concept")
    out = {}
    for period in cashflow.periods:
        children = edges[edges["period"] == period]
        raw = pd.to_numeric(
            values[period].reindex(children["concept"]), errors="coerce"
        )
        out[period] = (
            (raw.to_numpy() * children["weight"].astype(float)).sum()
            if len(children)
            else np.nan
        )
    return pd.Series(out)


def _working_capital_cash_impact(cashflow) -> pd.Series:
    return _cfo_children(cashflow, "IncreaseDecrease").fillna(0)


def _cfo_depreciation(cashflow) -> pd.Series:
    return _cfo_children(cashflow, "Depreciation")


@pytest.mark.data
def test_owner_earnings_memo_rows_hold_every_period(data_ticker: str) -> None:
    base = load_statement_set(data_ticker, "annual")
    income = base.income.frame
    pretax_rows = income[
        income["standard_concept"].eq(PRETAX_INCOME) & ~bool_flag(income, "dimension")
    ]
    assert not pretax_rows.empty, (data_ticker, "no pretax income row")
    items = oe.da_items(base.cashflow)
    assert not items.empty, (data_ticker, "no D&A item to set maintenance on")
    spec = AdjustmentSpec(
        oe.TYPE_ID, {**dict.fromkeys(items["row_id"], 50.0), oe.MAINTENANCE_NWC: 50.0}
    )
    run = apply_adjustments(base, [spec])
    assert run.applied == (spec,) and run.skipped == (), data_ticker

    periods = base.cashflow.periods
    pretax = pd.to_numeric(pretax_rows.iloc[0].reindex(periods), errors="coerce")
    da = _cfo_depreciation(base.cashflow).fillna(items[periods].fillna(0).sum())
    nwc = _working_capital_cash_impact(base.cashflow)
    with_pretax = [p for p in periods if pd.notna(pretax[p])]
    assert with_pretax, (data_ticker, "no period with pretax income")
    memo = run.statements.cashflow.frame.set_index("row_id")
    capex = memo.loc["adj_MaintenanceCapex"]
    working = memo.loc["adj_MaintenanceWorkingCapital"]
    earnings = memo.loc["adj_OwnerEarnings"]
    assert list(earnings[periods].dropna().index) == with_pretax
    for p in with_pretax:
        assert capex[p] == pytest.approx(0.5 * da[p]), (data_ticker, p)
        assert working[p] == pytest.approx(0.5 * nwc[p]), (data_ticker, p)
        assert earnings[p] == pytest.approx(
            pretax[p] + da[p] + nwc[p] - capex[p] - working[p]
        ), (data_ticker, p)
