"""Owner earnings: memo rows on the cash-flow statement.

``OE = pretax income + Σ D&A_i + ΔNWC − Σ pct_i·D&A_i − pct_nwc·ΔNWC``,
with ΔNWC on the CFO sign convention (cash impact of the working-capital
change rows) and maintenance amounts as user-chosen percentages.

D&A items (:func:`da_items`) are the note-reported D&A components (cash-flow
breakdown rows on ``DA_COMPONENT_AXIS``), else the D&A line itself, plus every
``da``-tagged row added by earlier adjustments (capitalized-opex
amortization). Each item's maintenance % is saved under its row id.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import pandas as pd

from src.adjustments.base import MEMO_TAG, AdjustmentResult, AdjustmentSpec, NewRow
from src.api.edgartools.standard_terms import (
    CFO,
    DA_COMPONENT_AXIS,
    DEPRECIATION_EXPENSE,
    NWC_ABSTRACT,
    NWC_PREFIX,
    PRETAX_INCOME,
)
from src.models.statement import Statement, StatementSet, bool_flag

TYPE_ID = "owner_earnings"
LABEL = "Owner earnings"

MAINTENANCE_NWC = "maintenance_nwc"


def from_prefs(rows: pd.DataFrame) -> AdjustmentSpec:
    return AdjustmentSpec(
        TYPE_ID, {str(r.base_concept): float(r.value) for r in rows.itertuples()}
    )


def _is_cfo(concept: str) -> bool:
    return concept.split("_")[-1].startswith(CFO.split("_")[-1])


def _cfo_weights(cashflow: Statement) -> dict[str, dict[str, float]]:
    """Some filings carry no operating calc tree at all, so a period whose
    tree lacks the concept takes the nearest period's CFO weight."""
    periods = cashflow.periods
    placed: dict[str, dict[str, float | None]] = {}
    for edge in cashflow.calc_edges.itertuples(index=False):
        weight = float(edge.weight) if _is_cfo(edge.parent_concept) else None
        placed.setdefault(edge.concept, {})[edge.period] = weight
    out = {}
    for concept, by_period in placed.items():
        known = [i for i, p in enumerate(periods) if by_period.get(p) is not None]
        if not known:
            continue
        nearest = {
            p: by_period.get(
                p, by_period[periods[min(known, key=lambda k: abs(k - i))]]
            )
            for i, p in enumerate(periods)
        }
        out[concept] = {p: w for p, w in nearest.items() if w is not None}
    return out | _balance_weights(cashflow, exclude=placed.keys())


def _balance_weights(
    cashflow: Statement, exclude: Collection[str]
) -> dict[str, dict[str, float]]:
    """XBRL requires a positive calc weight between concepts of the same
    balance type and a negative one between opposite ones, which signs a row
    the calc tree never places."""
    frame = cashflow.frame
    typed = frame[frame["balance"].notna()]
    cfo = typed.loc[typed["concept"].map(_is_cfo), "balance"]
    if cfo.empty:
        return {}
    typed = typed[~typed["concept"].isin(exclude)]
    return {
        concept: dict.fromkeys(cashflow.periods, 1.0 if bal == cfo.iloc[0] else -1.0)
        for concept, bal in zip(typed["concept"], typed["balance"], strict=True)
    }


def nwc_rows(cashflow: Statement) -> pd.DataFrame:
    """Working-capital change rows with values on the CFO sign (cash impact).

    Rows presented under the "changes in operating assets and liabilities"
    header, else any ``IncreaseDecreaseIn*`` concept, that sum into CFO.
    Value = calc weight into CFO (:func:`_cfo_weights`) × raw value.
    Columns: ``row_id, label`` + periods.
    """
    frame = cashflow.frame
    rows = frame[~bool_flag(frame, "dimension") & ~bool_flag(frame, "abstract")]
    under_header = rows["parent_abstract_concept"].eq(NWC_ABSTRACT)
    if not under_header.any():
        under_header = rows["concept"].str.split("_").str[-1].str.startswith(NWC_PREFIX)
    weights = _cfo_weights(cashflow)
    rows = rows[under_header & rows["concept"].isin(weights)]
    out = rows[["row_id", "label"]].copy()
    for period in cashflow.periods:
        raw = pd.to_numeric(rows[period], errors="coerce")
        weight = rows["concept"].map({c: w.get(period) for c, w in weights.items()})
        out[period] = raw * weight.astype(float)
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


def da_items(cashflow: Statement) -> pd.DataFrame:
    """D&A items, one row each: ``row_id, label`` + periods (raw values).

    Note-reported components when the cache has them, else the D&A line;
    then every ``da``-tagged adjustment row.
    """
    frame = cashflow.frame
    axis = frame.get("dimension_axis", pd.Series(None, index=frame.index))
    components = frame[axis.eq(DA_COMPONENT_AXIS)]
    if components.empty:
        components = frame[
            frame["standard_concept"].eq(DEPRECIATION_EXPENSE)
            & ~bool_flag(frame, "dimension")
        ].head(1)
    tagged = frame[frame["tags"].map(lambda t: "da" in tuple(t or ()))]
    items = pd.concat([components, tagged])
    out = items[["row_id", "label"]].copy()
    for period in cashflow.periods:
        out[period] = pd.to_numeric(items[period], errors="coerce")
    return out.reset_index(drop=True)


def components(ss: StatementSet) -> pd.DataFrame:
    """Per period: ``pretax``, ``da`` (Σ items), ``nwc`` (index = periods)."""
    income, cashflow = ss.income, ss.cashflow
    pretax = _first_value(income, income.frame["standard_concept"].eq(PRETAX_INCOME))
    items = da_items(cashflow)
    nwc = nwc_rows(cashflow)
    periods = [p for p in cashflow.periods if p in pretax]
    data = [
        {
            "pretax": pretax.get(p),
            "da": float(items[p].fillna(0).sum()),
            "nwc": float(pd.to_numeric(nwc[p], errors="coerce").fillna(0).sum()),
        }
        for p in periods
    ]
    return pd.DataFrame(data, index=periods)


def maintenance_da(items: pd.DataFrame, pcts: dict[str, float]) -> pd.Series:
    """Per period: Σ pct_i/100 · D&A_i over items (missing pct = 0)."""
    periods = [c for c in items.columns if c not in ("row_id", "label")]
    weights = items["row_id"].map(lambda r: pcts.get(r, 0.0) / 100)
    return items[periods].fillna(0).mul(weights, axis=0).sum()


def owner_earnings(
    parts: pd.DataFrame, maintenance: pd.Series, nwc_pct: float
) -> pd.DataFrame:
    out = parts.copy()
    out["maintenance_da"] = maintenance.reindex(out.index).fillna(0)
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
    nwc_pct = float(spec.params.get(MAINTENANCE_NWC, 0.0))
    pcts = {k: float(v) for k, v in spec.params.items() if k != MAINTENANCE_NWC}
    maintenance = maintenance_da(da_items(ss.cashflow), pcts)
    oe = owner_earnings(components(ss), maintenance, nwc_pct)
    rows = [
        (
            "adj_MaintenanceCapex",
            "Maintenance capex (maintenance share of D&A)",
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
    new_rows = []
    for concept, label, column, is_total in rows:
        new_rows.append(
            NewRow(
                "cashflow",
                concept,
                label,
                oe[column].dropna().to_dict(),
                tags=(MEMO_TAG,),
                is_total=is_total,
                after=after,
            )
        )
        after = concept  # keep the memo rows in order under CFO
    return AdjustmentResult(new_rows=new_rows)


def describe(spec: AdjustmentSpec) -> dict[str, Any]:
    return {
        "type": TYPE_ID,
        "label": (
            f"{LABEL}: maintenance % set on "
            f"{sum(k != MAINTENANCE_NWC for k in spec.params)} D&A item(s), "
            f"{spec.params.get(MAINTENANCE_NWC, 0):g}% of ΔNWC"
        ),
    }
