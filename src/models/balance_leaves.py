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
    label: str
    side: Side
    is_equity: bool
    chain_weight: float
    raw_value: float
    display_value: float

    @property
    def contribution(self) -> float:
        return self.chain_weight * self.raw_value


def balance_leaves(balance: Statement, period: str) -> list[BalanceLeaf]:
    graph = balance.calc_graph(period)
    totals = graph.totals
    frame = balance.frame
    rows = frame[~bool_flag(frame, "dimension") & ~bool_flag(frame, "abstract")]
    values = pd.to_numeric(rows[period], errors="coerce")
    signs = rows["preferred_sign"] if "preferred_sign" in rows.columns else None
    leaves: list[BalanceLeaf] = []
    for index, row in rows.iterrows():
        value, concept = values[index], row["concept"]
        if concept in totals or pd.isna(value):
            continue
        coefficients = {concept: 1.0, **graph.coefficients(concept)}
        root = next((r for r in _ROOT_SIDES if r in coefficients), None)
        if root is None:
            continue
        sign = -1.0 if signs is not None and signs[index] == -1 else 1.0
        leaves.append(
            BalanceLeaf(
                row_id=str(row["row_id"]),
                label=str(row["label"]),
                side=_ROOT_SIDES[root],
                is_equity=any(c in coefficients for c in EQUITY_PARENTS),
                chain_weight=coefficients[root],
                raw_value=float(value),
                display_value=sign * float(value),
            )
        )
    return leaves
