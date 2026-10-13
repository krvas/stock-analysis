"""Opex → capex: capitalize selected operating expenses over a useful life.

For each capitalized income row R with life N (raw signs, same-year
amortization start, no tax effect — ``specs/adjustments_architecture.md`` §7, §9):

- IS: R → 0; insert ``Amortization of capitalized R`` (tag ``da``) under R's
  calc parent with R's weight.
- BS: insert ``Capitalized R (net)`` under ``AssetsNoncurrent`` (else
  ``Assets``) and an equal equity offset under the equity total.
- CF: insert the amortization add-back under CFO and the capitalized spend
  as an outflow under CFI. Net income syncs from IS in the engine.

Parents resolve per period through the concepts the filing uses there. A
period whose calc trees can't carry all five rows stays as reported, with a
reason in ``AdjustmentResult.skipped``, so every statement still balances.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentResult, AdjustmentSpec, NewRow, Override
from src.api.edgartools.standard_terms import (
    ASSET_PARENTS,
    CFI_PARENTS,
    CFO_PARENTS,
    DEPRECIATION_EXPENSE,
    EQUITY_PARENTS,
    NET_INCOME_CONCEPTS,
)
from src.models.statement import Statement, StatementSet

TYPE_ID = "opex_to_capex"
LABEL = "Opex capitalized"


def from_prefs(rows: pd.DataFrame) -> AdjustmentSpec:
    return AdjustmentSpec(
        TYPE_ID,
        {"rows": {str(r.base_concept): float(r.value) for r in rows.itertuples()}},
    )


def schedule(spend: Mapping[str, float], life: int) -> tuple[dict, dict]:
    """``(amortization, net_asset)`` per period from per-period spend.

    Periods are ISO dates; spend in period t amortizes evenly over t..t+N-1.
    """
    ordered = sorted(spend)
    amort: dict[str, float] = {}
    net: dict[str, float] = {}
    for i, period in enumerate(ordered):
        window = [spend[ordered[i - k]] for k in range(life) if i - k >= 0]
        amort[period] = sum(window) / life
        net[period] = sum(
            spend[ordered[i - k]] * (1 - (k + 1) / life)
            for k in range(life)
            if i - k >= 0
        )
    return amort, net


@dataclass(frozen=True)
class _Parents:
    """Calc parents of the inserted rows in one period."""

    expense: str
    expense_weight: float
    asset: str
    equity: str
    cfo: str
    cfi: str


def _period_tree(statement: Statement, period: str) -> pd.DataFrame:
    edges = statement.calc_edges
    return edges[edges["period"] == period]


def _first_total(tree: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    """First candidate with children in ``tree``: a total the engine can recompute."""
    totals = set(tree["parent_concept"])
    return next((c for c in candidates if c in totals), None)


def _parents(ss: StatementSet, concept: str, period: str) -> _Parents | str:
    """Where ``concept``'s rows hang in ``period``, or why they can't."""
    income = _period_tree(ss.income, period)
    parent_of = dict(zip(income["concept"], income["parent_concept"], strict=True))
    weight_of = dict(zip(income["concept"], income["weight"], strict=True))
    ancestors, node = [], concept
    while node in parent_of and parent_of[node] not in ancestors:
        node = parent_of[node]
        ancestors.append(node)
    if not ancestors:
        return "the income statement does not total it"
    balance = _period_tree(ss.balance, period)
    asset = _first_total(balance, ASSET_PARENTS)
    equity = _first_total(balance, EQUITY_PARENTS)
    if asset is None or equity is None:
        return "the balance sheet does not total its assets and equity"
    cashflow = _period_tree(ss.cashflow, period)
    cfo = _first_total(cashflow, CFO_PARENTS)
    cfi = _first_total(cashflow, CFI_PARENTS)
    if cfo is None or cfi is None:
        return "the cash flow statement does not total operating and investing cash"
    starts = set(cashflow.loc[cashflow["parent_concept"] == cfo, "concept"])
    starts &= set(ancestors) & set(NET_INCOME_CONCEPTS)
    if not starts:
        return "the cash flow statement does not start from net income"
    if len(starts) > 1:
        return "the cash flow statement adds net income in more than once"
    return _Parents(ancestors[0], float(weight_of[concept]), asset, equity, cfo, cfi)


def _slot(parents: dict[str, _Parents], slot: str) -> dict[str, Any]:
    return {period: getattr(found, slot) for period, found in parents.items()}


def _before(statement: Statement, concepts: tuple[str, ...]) -> str | None:
    """Row id just before the first of ``concepts`` present, to insert above it."""
    frame = statement.frame
    for concept in concepts:
        match = frame.index[frame["concept"] == concept]
        if len(match) > 0:
            return None if match[0] == 0 else str(frame.at[match[0] - 1, "row_id"])
    return None


def apply(ss: StatementSet, spec: AdjustmentSpec) -> AdjustmentResult:
    applied: dict[str, Any] = {}
    result = AdjustmentResult(applied_params={**spec.params, "rows": applied})
    income = ss.income
    frame = income.frame
    for row_id, years in dict(spec.params.get("rows", {})).items():
        life = max(round(years), 1)
        match = frame[frame["row_id"] == row_id]
        if match.empty:
            result.skipped.append(f"saved row {row_id} is not in this filing")
            continue
        row = match.iloc[0]
        concept = str(row["concept"])
        name = str(row["label"])
        local = concept.split("_", 1)[-1]
        reported = {
            p: float(row[p]) for p in income.periods if pd.notna(pd.to_numeric(row[p]))
        }
        if not reported:
            result.skipped.append(f"{name} has no reported values")
            continue
        parents: dict[str, _Parents] = {}
        gaps: dict[str, list[str]] = {}
        for period in reported:
            found = _parents(ss, concept, period)
            if isinstance(found, str):
                gaps.setdefault(found, []).append(period)
            else:
                parents[period] = found
        result.skipped.extend(
            f"{name} left as an expense in {', '.join(sorted(periods))}: {reason}"
            for reason, periods in gaps.items()
        )
        if not parents:
            continue
        applied[row_id] = years
        # A period left as an expense capitalizes nothing; later periods
        # still amortize what earlier periods capitalized.
        amort, net = schedule(
            {p: v if p in parents else 0.0 for p, v in reported.items()}, life
        )
        amort = {p: amort[p] for p in parents}
        net = {p: net[p] for p in parents}
        spend = {p: reported[p] for p in parents}

        result.overrides.append(Override("income", row_id, {p: 0.0 for p in spend}))
        result.new_rows.append(
            NewRow(
                "income",
                f"adj_Amortization{local}",
                f"Amortization of capitalized {name.lower()}",
                amort,
                parent_concept=_slot(parents, "expense"),
                weight=_slot(parents, "expense_weight"),
                tags=("da",),
                after=row_id,
            )
        )
        balance = ss.balance
        result.new_rows.append(
            NewRow(
                "balance",
                f"adj_Capitalized{local}",
                f"Capitalized {name.lower()} (net)",
                net,
                parent_concept=_slot(parents, "asset"),
                after=_before(balance, ASSET_PARENTS),
            )
        )
        result.new_rows.append(
            NewRow(
                "balance",
                f"adj_EquityCapitalized{local}",
                f"Equity effect of capitalized {name.lower()}",
                net,
                parent_concept=_slot(parents, "equity"),
                after=_before(balance, EQUITY_PARENTS),
            )
        )
        cashflow = ss.cashflow
        result.new_rows.append(
            NewRow(
                "cashflow",
                f"adj_Amortization{local}",
                f"Amortization of capitalized {name.lower()}",
                amort,
                parent_concept=_slot(parents, "cfo"),
                tags=("da",),
                after=_dna_row(cashflow) or _before(cashflow, CFO_PARENTS),
            )
        )
        result.new_rows.append(
            NewRow(
                "cashflow",
                f"adj_Capitalized{local}",
                f"Capitalized {name.lower()}",
                spend,
                parent_concept=_slot(parents, "cfi"),
                weight=-1.0,
                after=_before(cashflow, CFI_PARENTS),
            )
        )
    return result


def _dna_row(cashflow: Statement) -> str | None:
    frame = cashflow.frame
    match = frame[frame["standard_concept"].eq(DEPRECIATION_EXPENSE)]
    return None if match.empty else str(match["row_id"].iloc[0])


def describe(spec: AdjustmentSpec) -> dict[str, Any]:
    return {"type": TYPE_ID, "label": f"{LABEL} ({len(spec.params.get('rows', {}))})"}
