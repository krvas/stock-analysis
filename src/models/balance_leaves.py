"""Balance-sheet leaves: the line items that add up to each side's total.

A leaf is a non-dimensional, non-abstract balance-sheet row with a numeric
value in the period and no calc children in that period's calc tree. Its side
is the root of its calc-parent chain (total assets, or total liabilities and
equity); rows whose chain reaches neither root are not leaves. A leaf whose
chain passes an equity parent is equity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.api.edgartools.standard_terms import (
    BALANCE_ASSETS_ROOT,
    BALANCE_LIABILITIES_EQUITY_ROOT,
    EQUITY_PARENTS,
)
from src.models.statement import Statement, bool_flag

Side = Literal["assets", "liabilities"]

_ROOT_SIDES: Final[dict[str, Side]] = {
    BALANCE_ASSETS_ROOT: "assets",
    BALANCE_LIABILITIES_EQUITY_ROOT: "liabilities",
}


@dataclass(frozen=True)
class BalanceLeaf:
    row_id: str
    concept: str
    label: str
    side: Side
    is_equity: bool
    weight: float
    value: float
    display_value: float

    @property
    def contribution(self) -> float:
        """What this leaf adds to its side's total."""
        return self.weight * self.value


def balance_leaves(balance: Statement, period: str) -> list[BalanceLeaf]:
    """The leaves of ``period`` in frame order.

    ``weight`` is the product of calc weights along the chain to the root in
    that period; ``value`` is raw, ``display_value`` has ``preferred_sign``
    applied.
    """
    edges = balance.calc_edges
    edges = edges[edges["period"] == period]
    parent = dict(zip(edges["concept"], edges["parent_concept"], strict=True))
    edge_weight = dict(zip(edges["concept"], edges["weight"], strict=True))
    parents = set(parent.values())
    frame = balance.frame
    rows = frame[~bool_flag(frame, "dimension") & ~bool_flag(frame, "abstract")]
    values = pd.to_numeric(rows[period], errors="coerce")
    signs = rows["preferred_sign"] if "preferred_sign" in rows.columns else None
    leaves: list[BalanceLeaf] = []
    for index, row in rows.iterrows():
        value, concept = values[index], row["concept"]
        if concept in parents or pd.isna(value):
            continue
        chain, node, weight = [concept], concept, 1.0
        while node in parent and parent[node] not in chain:
            weight *= float(edge_weight[node])
            node = parent[node]
            chain.append(node)
        side = _ROOT_SIDES.get(chain[-1])
        if side is None:
            continue
        sign = -1.0 if signs is not None and signs[index] == -1 else 1.0
        leaves.append(
            BalanceLeaf(
                row_id=str(row["row_id"]),
                concept=str(concept),
                label=str(row["label"]),
                side=side,
                is_equity=any(c in EQUITY_PARENTS for c in chain),
                weight=weight,
                value=float(value),
                display_value=sign * float(value),
            )
        )
    return leaves
