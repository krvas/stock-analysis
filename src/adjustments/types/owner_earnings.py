"""Owner earnings: memo rows on the cash-flow statement.

``OE = pretax income + Σ D&A_i + ΔNWC − Σ pct_i·D&A_i − pct_nwc·ΔNWC``,
with ΔNWC on the CFO sign convention (cash impact of the working-capital
change rows) and maintenance amounts as user-chosen percentages.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import MEMO_TAG, AdjustmentResult, AdjustmentSpec, NewRow
from src.api.edgartools.standard_terms import (
    CFO,
    DA_COMPONENT_AXIS,
    DA_REMAINDER_TOLERANCE,
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


LINE_SLOT_SUFFIX = " (years without a note breakdown)"


def _local_name(concepts: pd.Series) -> pd.Series:
    return concepts.fillna("").str.split("_").str[-1]


def _da_lines(cashflow: Statement) -> pd.DataFrame:
    frame = cashflow.frame
    rows = frame[~bool_flag(frame, "dimension") & ~bool_flag(frame, "abstract")]
    edges = cashflow.calc_edges
    cfo = _local_name(edges["parent_concept"]).str.startswith(CFO.split("_")[-1])
    into_cfo = edges.loc[cfo, "concept"]
    extension = (
        rows["standard_concept"].isna()
        & _local_name(rows["concept"]).str.startswith("Depreciation")
        & rows["concept"].isin(into_cfo)
    )
    return pd.concat(
        [rows[rows["standard_concept"].eq(DEPRECIATION_EXPENSE)], rows[extension]]
    )


def _resolve_period(
    line: tuple[str, float] | None, parts: dict[str, float]
) -> dict[str, float]:
    """One period's D&A by slot id; sums to the line whenever there is one."""
    if line is None:
        return parts
    line_id, total = line
    if parts and abs(sum(parts.values()) - total) <= DA_REMAINDER_TOLERANCE:
        return parts
    return {line_id: total}


def da_items(cashflow: Statement) -> pd.DataFrame:
    """D&A items, one row each: ``row_id, label`` + periods (raw values, NaN
    where the slot does not apply that period).

    Slots: each note component, the D&A line (periods the components do not
    explain), then every ``da``-tagged adjustment row. Slots blank in every
    period are dropped.
    """
    frame = cashflow.frame
    axis = frame.get("dimension_axis", pd.Series(None, index=frame.index))
    parts = frame[axis.eq(DA_COMPONENT_AXIS)]
    lines = _da_lines(cashflow)
    slots = parts[["row_id", "label"]]
    if not lines.empty:
        slots = pd.concat([slots, lines[["row_id", "label"]].head(1)])
    slots = slots.reset_index(drop=True)
    line_id = lines["row_id"].iloc[0] if not lines.empty else None
    for period in cashflow.periods:
        line = pd.to_numeric(lines[period], errors="coerce").dropna()
        reported = pd.to_numeric(parts[period], errors="coerce")
        values = _resolve_period(
            (line_id, float(line.iloc[0])) if len(line) else None,
            {
                str(r): float(v)
                for r, v in zip(parts["row_id"], reported, strict=True)
                if pd.notna(v)
            },
        )
        slots[period] = slots["row_id"].map(values).astype(float)
    slots = slots[slots[cashflow.periods].notna().any(axis=1)].copy()
    if line_id in set(slots["row_id"]) and len(slots) > 1:
        slots.loc[slots["row_id"] == line_id, "label"] += LINE_SLOT_SUFFIX
    tagged = frame[frame["tags"].map(lambda t: "da" in tuple(t or ()))]
    adjustments = tagged[["row_id", "label"]].copy()
    for period in cashflow.periods:
        adjustments[period] = pd.to_numeric(tagged[period], errors="coerce")
    return pd.concat([slots, adjustments]).reset_index(drop=True)


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
