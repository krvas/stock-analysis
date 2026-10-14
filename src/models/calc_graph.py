"""One period's calc network as a graph: each concept with all its calc parents.

XBRL calc networks are DAGs: a filer may sum one concept into two totals
(JPM's loans into both net loans and Assets). Every walk over a period's calc
tree goes through :class:`CalcGraph`, so no caller assumes one parent per
concept. Walks stop at a concept already on the current path, so a filer's
calc cycle (invalid XBRL) ends them instead of looping.

Pure: pandas only, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


class CalcGraph:
    """Concept → ``{parent: weight}`` for one period (raw signs)."""

    def __init__(self, parents: Mapping[str, Mapping[str, float]]) -> None:
        self._parents = {c: dict(p) for c, p in parents.items()}
        self._depth: dict[str, int] = {}

    @classmethod
    def from_edges(cls, edges: pd.DataFrame) -> CalcGraph:
        """From rows of ``concept, parent_concept, weight`` (one period's)."""
        parents: dict[str, dict[str, float]] = {}
        for concept, parent, weight in zip(
            edges["concept"], edges["parent_concept"], edges["weight"], strict=True
        ):
            parents.setdefault(concept, {})[parent] = float(weight)
        return cls(parents)

    @property
    def totals(self) -> frozenset[str]:
        """Concepts with at least one calc child."""
        return frozenset(p for parents in self._parents.values() for p in parents)

    def parents(self, concept: str) -> dict[str, float]:
        """Every total ``concept`` sums into, with its weight there."""
        return dict(self._parents.get(concept, {}))

    def ancestors(self, concept: str) -> frozenset[str]:
        """Every concept above ``concept`` on any path."""
        seen: set[str] = set()
        stack = list(self._parents.get(concept, {}))
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(self._parents.get(node, {}))
        return frozenset(seen)

    def coefficients(self, concept: str) -> dict[str, float]:
        """Per ancestor, how much one unit of ``concept`` adds to it: the sum
        over every path of the product of the edge weights."""
        out: dict[str, float] = {}

        def walk(node: str, weight: float, path: frozenset[str]) -> None:
            for parent, edge in self._parents.get(node, {}).items():
                if parent in path:
                    continue
                out[parent] = out.get(parent, 0.0) + weight * edge
                walk(parent, weight * edge, path | {parent})

        walk(concept, 1.0, frozenset({concept}))
        return out

    def depth(self, concept: str) -> int:
        """Longest path from ``concept`` up to a root: a child is always deeper
        than each of its parents, so deepest-first visits children first."""
        return self._longest(concept, frozenset())

    def _longest(self, concept: str, path: frozenset[str]) -> int:
        if concept in self._depth:
            return self._depth[concept]
        above = [p for p in self._parents.get(concept, {}) if p not in path]
        depth = 1 + max((self._longest(p, path | {concept}) for p in above), default=-1)
        self._depth[concept] = depth
        return depth
