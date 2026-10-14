from __future__ import annotations

import pandas as pd

from src.models.calc_graph import CalcGraph


def _graph(*arcs: tuple[str, str, float]) -> CalcGraph:
    return CalcGraph.from_edges(
        pd.DataFrame(arcs, columns=["concept", "parent_concept", "weight"])
    )


# JPM: loans and allowance sum into both net loans and Assets.
JPM = _graph(
    ("Loans", "LoansNet", 1.0),
    ("Allowance", "LoansNet", -1.0),
    ("Loans", "Assets", 1.0),
    ("Allowance", "Assets", -1.0),
    ("Cash", "Assets", 1.0),
)


def test_parents_lists_every_total_with_its_weight() -> None:
    assert JPM.parents("Allowance") == {"LoansNet": -1.0, "Assets": -1.0}
    assert JPM.parents("Assets") == {}
    assert JPM.totals == frozenset({"LoansNet", "Assets"})


def test_ancestors_follow_every_path() -> None:
    graph = _graph(("X", "A", 1.0), ("X", "B", 1.0), ("B", "Root", -1.0))
    assert graph.ancestors("X") == frozenset({"A", "B", "Root"})
    assert graph.ancestors("Root") == frozenset()


def test_coefficients_sum_weights_over_every_path() -> None:
    graph = _graph(
        ("X", "Sub", -1.0),
        ("Sub", "Root", -1.0),
        ("X", "Other", 1.0),
        ("Other", "Root", 1.0),
    )
    assert graph.coefficients("X") == {"Sub": -1.0, "Other": 1.0, "Root": 2.0}
    assert JPM.coefficients("Allowance") == {"LoansNet": -1.0, "Assets": -1.0}


def test_depth_is_the_longest_path_to_a_root() -> None:
    graph = _graph(("X", "Root", 1.0), ("X", "Sub", 1.0), ("Sub", "Root", 1.0))
    assert [graph.depth(c) for c in ("Root", "Sub", "X")] == [0, 1, 2]


def test_a_cycle_ends_every_walk() -> None:
    graph = _graph(("A", "B", 1.0), ("B", "A", 1.0), ("A", "Root", 1.0))
    assert graph.ancestors("A") >= {"B", "Root"}
    assert graph.depth("A") >= 1
    assert graph.coefficients("A")["Root"] == 1.0
