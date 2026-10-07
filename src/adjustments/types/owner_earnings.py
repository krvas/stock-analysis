"""Owner earnings: memo rows on the cash-flow statement.

``OE = pretax income + D&A + ΔNWC − maintenance D&A − maintenance ΔNWC``,
with ΔNWC on the CFO sign convention (cash impact of the working-capital
change rows) and maintenance amounts as user-chosen percentages. D&A and
pretax income are read *after* earlier adjustments (opex → capex), so the
capitalized-expense amortization (tag ``da``) is included.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentResult, AdjustmentSpec, NewRow
from src.models.statement import Statement, StatementSet, bool_flag

TYPE_ID = "owner_earnings"
LABEL = "Owner earnings"

MAINTENANCE_DA = "maintenance_da"
MAINTENANCE_NWC = "maintenance_nwc"

NWC_ABSTRACT = "us-gaap_IncreaseDecreaseInOperatingCapitalAbstract"
NWC_PREFIX = "IncreaseDecreaseIn"
CFO = "us-gaap_NetCashProvidedByUsedInOperatingActivities"


def from_prefs(rows: pd.DataFrame) -> AdjustmentSpec:
    return AdjustmentSpec(
        TYPE_ID, {str(r.base_concept): float(r.value) for r in rows.itertuples()}
    )


def _edge_weights(cashflow: Statement) -> dict[tuple[str, str], float]:
    edges = cashflow.calc_edges
    return {
        (row.period, row.concept): float(row.weight)
        for row in edges.itertuples(index=False)
    }


def nwc_rows(cashflow: Statement) -> pd.DataFrame:
    """Working-capital change rows with values on the CFO sign (cash impact).

    Rows presented under the "changes in operating assets and liabilities"
    header, else any ``IncreaseDecreaseIn*`` concept summed into CFO. Value =
    that period's calc weight × raw value. Columns: ``row_id, label`` +
    periods.
    """
    frame = cashflow.frame
    rows = frame[~bool_flag(frame, "dimension") & ~bool_flag(frame, "abstract")]
    under_header = rows["parent_abstract_concept"].eq(NWC_ABSTRACT)
    if not under_header.any():
        under_header = rows["concept"].str.split("_").str[-1].str.startswith(NWC_PREFIX)
    rows = rows[under_header]
    weights = _edge_weights(cashflow)
    out = rows[["row_id", "label"]].copy()
    for period in cashflow.periods:
        raw = pd.to_numeric(rows[period], errors="coerce")
        out[period] = [
            v * weights.get((period, c), 1.0) if pd.notna(v) else None
            for v, c in zip(raw, rows["concept"], strict=True)
        ]
    return out[out[cashflow.periods].notna().any(axis=1)].reset_index(drop=True)


def _first_value(statement: Statement, mask: pd.Series) -> dict[str, float]:
    frame = statement.frame
    rows = frame[mask & ~bool_flag(frame, "dimension")]
    if rows.empty:
        return {}
    row = rows.iloc[0]
    return {
        p: float(row[p]) for p in statement.periods if pd.notna(pd.to_numeric(row[p]))
    }


def components(ss: StatementSet) -> pd.DataFrame:
    """Per period: ``pretax``, ``da``, ``nwc`` (index = periods, newest first)."""
    income, cashflow = ss.income, ss.cashflow
    pretax = _first_value(
        income, income.frame["standard_concept"].eq("PretaxIncomeLoss")
    )
    da = _first_value(
        cashflow, cashflow.frame["standard_concept"].eq("DepreciationExpense")
    )
    tagged = cashflow.frame[
        cashflow.frame["tags"].map(lambda t: "da" in tuple(t or ()))
    ]
    nwc = nwc_rows(cashflow)
    periods = [p for p in cashflow.periods if p in pretax]
    data = []
    for p in periods:
        extra = pd.to_numeric(tagged[p], errors="coerce").fillna(0).sum()
        data.append(
            {
                "pretax": pretax.get(p),
                "da": da.get(p, 0.0) + float(extra),
                "nwc": float(pd.to_numeric(nwc[p], errors="coerce").fillna(0).sum()),
            }
        )
    return pd.DataFrame(data, index=periods)


def owner_earnings(parts: pd.DataFrame, da_pct: float, nwc_pct: float) -> pd.DataFrame:
    out = parts.copy()
    out["maintenance_da"] = out["da"] * da_pct / 100
    out["maintenance_nwc"] = out["nwc"] * nwc_pct / 100
    out["owner_earnings"] = (
        out["pretax"]
        + out["da"]
        + out["nwc"]
        - out["maintenance_da"]
        - out["maintenance_nwc"]
    )
    return out


def apply(ss: StatementSet, spec: AdjustmentSpec) -> AdjustmentResult:
    da_pct = float(spec.params.get(MAINTENANCE_DA, 0.0))
    nwc_pct = float(spec.params.get(MAINTENANCE_NWC, 0.0))
    oe = owner_earnings(components(ss), da_pct, nwc_pct)
    rows = [
        (
            "adj_MaintenanceCapex",
            f"Maintenance capex ({da_pct:g}% of D&A)",
            "maintenance_da",
            False,
        ),
        (
            "adj_MaintenanceWorkingCapital",
            f"Maintenance working capital ({nwc_pct:g}% of ΔNWC)",
            "maintenance_nwc",
            False,
        ),
        ("adj_OwnerEarnings", "Owner earnings", "owner_earnings", True),
    ]
    frame = ss.cashflow.frame
    cfo = frame.loc[frame["concept"] == CFO, "row_id"]
    after = str(cfo.iloc[0]) if len(cfo) else None
    return AdjustmentResult(
        new_rows=[
            NewRow(
                "cashflow",
                concept,
                label,
                oe[column].dropna().to_dict(),
                is_total=is_total,
                after=after,
            )
            for concept, label, column, is_total in rows
        ]
    )


def describe(spec: AdjustmentSpec) -> dict[str, Any]:
    return {
        "type": TYPE_ID,
        "label": (
            f"{LABEL}: maintenance {spec.params.get(MAINTENANCE_DA, 0):g}% of D&A, "
            f"{spec.params.get(MAINTENANCE_NWC, 0):g}% of ΔNWC"
        ),
    }
