"""Opex → capex: capitalize selected operating expenses over a useful life.

For each capitalized income row R with life N (raw signs, same-year
amortization start, no tax effect — ``specs/adjustments_architecture.md`` §7, §9):

- IS: R → 0; insert ``Amortization of capitalized R`` (tag ``da``) under R's
  calc parent with R's weight.
- BS: insert ``Capitalized R (net)`` under ``AssetsNoncurrent`` (else
  ``Assets``) and an equal equity offset under ``StockholdersEquity``.
- CF: insert the amortization add-back under CFO and the capitalized spend
  as an outflow under CFI. Net income syncs from IS in the engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentResult, AdjustmentSpec, NewRow, Override
from src.models.statement import Statement, StatementSet

TYPE_ID = "opex_to_capex"
LABEL = "Opex capitalized"

ASSET_PARENTS = ("us-gaap_AssetsNoncurrent", "us-gaap_Assets")
EQUITY_PARENTS = (
    "us-gaap_StockholdersEquity",
    "us-gaap_StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
CFO = "us-gaap_NetCashProvidedByUsedInOperatingActivities"
CFI = "us-gaap_NetCashProvidedByUsedInInvestingActivities"


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


def _first_parent(statement: Statement, candidates: tuple[str, ...]) -> dict:
    edges = statement.calc_edges
    parents: dict[str, str] = {}
    for period in statement.periods:
        tree = edges[edges["period"] == period]
        present = set(tree["parent_concept"]) | set(tree["concept"])
        for concept in candidates:
            if concept in present:
                parents[period] = concept
                break
    return parents


def _before(statement: Statement, concept: str) -> str | None:
    """Row id just before ``concept``'s row, to insert a row above that total."""
    frame = statement.frame
    match = frame.index[frame["concept"] == concept]
    if len(match) == 0 or match[0] == 0:
        return None
    return str(frame.at[match[0] - 1, "row_id"])


def apply(ss: StatementSet, spec: AdjustmentSpec) -> AdjustmentResult:
    result = AdjustmentResult()
    income = ss.income
    frame = income.frame
    for row_id, years in dict(spec.params.get("rows", {})).items():
        life = max(round(years), 1)
        match = frame[frame["row_id"] == row_id]
        if match.empty:
            continue
        row = match.iloc[0]
        concept = str(row["concept"])
        name = str(row["label"])
        local = concept.split("_", 1)[-1]
        spend = {
            p: float(row[p]) for p in income.periods if pd.notna(pd.to_numeric(row[p]))
        }
        if not spend:
            continue
        amort, net = schedule(spend, life)
        tree = income.calc_edges[income.calc_edges["concept"] == concept]
        is_parent = dict(zip(tree["period"], tree["parent_concept"], strict=True))
        weight = float(tree["weight"].iloc[0]) if len(tree) else 1.0

        result.overrides.append(Override("income", row_id, {p: 0.0 for p in spend}))
        result.new_rows.append(
            NewRow(
                "income",
                f"adj_Amortization{local}",
                f"Amortization of capitalized {name.lower()}",
                amort,
                parent_concept=is_parent,
                weight=weight,
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
                parent_concept=_first_parent(balance, ASSET_PARENTS),
                after=_before(balance, ASSET_PARENTS[0])
                or _before(balance, ASSET_PARENTS[1]),
            )
        )
        result.new_rows.append(
            NewRow(
                "balance",
                f"adj_EquityCapitalized{local}",
                f"Equity effect of capitalized {name.lower()}",
                net,
                parent_concept=_first_parent(balance, EQUITY_PARENTS),
                after=_before(balance, EQUITY_PARENTS[0]),
            )
        )
        cashflow = ss.cashflow
        result.new_rows.append(
            NewRow(
                "cashflow",
                f"adj_Amortization{local}",
                f"Amortization of capitalized {name.lower()}",
                amort,
                parent_concept=CFO,
                tags=("da",),
                after=_dna_row(cashflow) or _before(cashflow, CFO),
            )
        )
        result.new_rows.append(
            NewRow(
                "cashflow",
                f"adj_Capitalized{local}",
                f"Capitalized {name.lower()}",
                spend,
                parent_concept=CFI,
                weight=-1.0,
                after=_before(cashflow, CFI),
            )
        )
    return result


def _dna_row(cashflow: Statement) -> str | None:
    frame = cashflow.frame
    match = frame[frame["standard_concept"].eq("DepreciationExpense")]
    return None if match.empty else str(match["row_id"].iloc[0])


def describe(spec: AdjustmentSpec) -> dict[str, Any]:
    return {"type": TYPE_ID, "label": f"{LABEL} ({len(spec.params.get('rows', {}))})"}
