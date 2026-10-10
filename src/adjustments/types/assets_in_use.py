"""Assets in use: Gross and Net Assets in Use as balance-sheet memo rows.

Per period, over the balance-sheet leaves (:mod:`src.models.balance_leaves`)
with contribution ``c = effective weight × raw value``:

- ``Gross = total assets − Σ_assets c_i · (1 − pct_i/100)``
- ``Net = Gross − Σ_netted liabilities c_j``

Params map row id → value: a % in use (default 100) for an asset leaf, 1.0
for a netted liability leaf. Keys are classified against each period's
leaves, so a % applies only where its row is a leaf and keys for rows that no
longer exist are ignored. Equity is never netted.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.adjustments.base import AdjustmentResult, AdjustmentSpec, NewRow
from src.api.edgartools.standard_terms import BALANCE_ASSETS_ROOT
from src.models.balance_leaves import balance_leaves
from src.models.statement import Statement, StatementSet

TYPE_ID = "assets_in_use"
LABEL = "Assets in use"
APPLIES_BY_DEFAULT = True

GROSS_CONCEPT = "adj_GrossAssetsInUse"
NET_CONCEPT = "adj_NetAssetsInUse"
NETTED = 1.0


def from_prefs(rows: pd.DataFrame) -> AdjustmentSpec:
    return AdjustmentSpec(
        TYPE_ID, {str(r.base_concept): float(r.value) for r in rows.itertuples()}
    )


def total_assets(balance: Statement) -> tuple[str | None, dict[str, float]]:
    """The total assets row id and its values by period (raw signs)."""
    rows = balance.find(concept=BALANCE_ASSETS_ROOT)
    if rows.empty:
        return None, {}
    row = rows.iloc[0]
    values = pd.to_numeric(row[balance.periods], errors="coerce")
    return str(row["row_id"]), values.dropna().astype(float).to_dict()


def _gross_and_net(
    balance: Statement, total: dict[str, float], params: dict[str, float]
) -> dict[str, tuple[float, float]]:
    """``period → (gross, net)`` for every period with total assets."""
    out: dict[str, tuple[float, float]] = {}
    if not params:
        return {period: (reported, reported) for period, reported in total.items()}
    for period, reported in total.items():
        not_in_use = netted = 0.0
        for leaf in balance_leaves(balance, period):
            saved = params.get(leaf.row_id)
            if leaf.side == "assets" and saved is not None:
                not_in_use += leaf.contribution * (1 - saved / 100)
            elif leaf.side == "liabilities" and not leaf.is_equity and saved == NETTED:
                netted += leaf.contribution
        gross = reported - not_in_use
        out[period] = (gross, gross - netted)
    return out


def apply(ss: StatementSet, spec: AdjustmentSpec) -> AdjustmentResult:
    params = {str(k): float(v) for k, v in spec.params.items()}
    after, total = total_assets(ss.balance)
    if not total:
        raise ValueError("balance sheet has no total assets")
    values = _gross_and_net(ss.balance, total, params)
    return AdjustmentResult(
        new_rows=[
            NewRow(
                "balance",
                GROSS_CONCEPT,
                "Gross assets in use",
                {p: gross for p, (gross, _) in values.items()},
                after=after,
            ),
            NewRow(
                "balance",
                NET_CONCEPT,
                "Net assets in use",
                {p: net for p, (_, net) in values.items()},
                after=GROSS_CONCEPT,
            ),
        ]
    )


def describe(spec: AdjustmentSpec) -> dict[str, Any]:
    # Without the balance sheet a saved key can't be told asset from
    # liability, so describe counts every choice that differs from a default.
    changed = sum(float(v) != 100 for v in spec.params.values())
    return {"type": TYPE_ID, "label": f"{LABEL}: {changed} line(s) changed"}
