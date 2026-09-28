"""Tests for the adjustment-preference re-keying CLI (synthetic statements)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.database.wizard_manager import WizardDatabaseManager
from src.models.statement import Statement, StatementSet
from src.pipelines.convert_adjustment_pref_keys import convert_pref_keys

P1 = "2024-12-31"


def _statement_set(ticker: str, period: str) -> StatementSet:
    income = Statement(
        pd.DataFrame(
            {
                "concept": [
                    "us-gaap_ResearchAndDevelopmentExpense",
                    "us-gaap_ResearchAndDevelopmentExpense",
                    "acme_CustomOpex",
                    "us-gaap_SellingExpense",
                    "us-gaap_MarketingExpense",
                ],
                "label": ["R&D", "R&D (segment)", "Custom", "Selling", "Marketing"],
                "standard_concept": [
                    "ResearchAndDevelopmentExpenses",
                    "ResearchAndDevelopmentExpenses",
                    None,
                    "SellingGeneralAndAdminExpenses",
                    "SellingGeneralAndAdminExpenses",
                ],
                "dimension": [False, True, False, False, False],
                "dimension_axis": [None, "srt_SegmentsAxis", None, None, None],
                "dimension_member": [None, "acme_ChipsMember", None, None, None],
                P1: [100.0, 60.0, 5.0, 20.0, 10.0],
            }
        ),
        "income",
    )
    empty = pd.DataFrame({"concept": pd.Series(dtype=str), P1: pd.Series(dtype=float)})
    return StatementSet(
        income=income,
        balance=Statement(empty, "balance"),
        cashflow=Statement(empty, "cashflow"),
        periods=(P1,),
    )


def _pref(base_concept: str, **overrides: object) -> dict[str, object]:
    row = {
        "ticker": "ACME",
        "exchange": "NASDAQ",
        "statement": "BS",
        "adjustment_type": "opex_to_capex",
        "base_concept": base_concept,
        "base_concept_statement": "PL",
        "value": 5.0,
    }
    row.update(overrides)
    return row


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "wizard.duckdb"
    with WizardDatabaseManager(path) as db:
        db.initialize_schema()
    return path


def _seed(db_path: Path, rows: list[dict[str, object]]) -> None:
    with WizardDatabaseManager(db_path) as db:
        db.upsert_adjustment_preferences(pd.DataFrame(rows))


def _keys(db_path: Path) -> dict[str, str]:
    with WizardDatabaseManager(db_path, read_only=True) as db:
        prefs = db.read_all_adjustment_preferences()
    return dict(zip(prefs["adjustment_id"], prefs["base_concept"]))


def _run(db_path: Path, **kwargs: object):
    return convert_pref_keys(db_path=db_path, load_set=_statement_set, **kwargs)


def test_converts_by_standard_concept(db_path: Path) -> None:
    _seed(db_path, [_pref("ResearchAndDevelopmentExpenses", value=7.0)])
    counts = _run(db_path)
    assert counts["converted"] == 1
    with WizardDatabaseManager(db_path, read_only=True) as db:
        prefs = db.read_all_adjustment_preferences()
    row = prefs.iloc[0]
    # Dimensional R&D row is ignored; the rest of the pref is kept.
    assert row["base_concept"] == "us-gaap_ResearchAndDevelopmentExpense"
    assert row["value"] == 7.0
    assert row["adjustment_id"] == "0"
    assert row["statement"] == "BS"


def test_converts_by_concept(db_path: Path) -> None:
    def loader(ticker: str, period: str) -> StatementSet:
        base = _statement_set(ticker, period)
        frame = base.income.frame.drop(columns=["row_id"]).copy()
        # Row id differs from concept (repeat within a filing) so the
        # concept match is the only way to find it.
        frame.loc[frame["concept"] == "acme_CustomOpex", "row_id"] = "acme_CustomOpex#2"
        frame["row_id"] = frame["row_id"].fillna(base.income.frame["row_id"])
        return StatementSet(
            income=Statement(frame, "income"),
            balance=base.balance,
            cashflow=base.cashflow,
            periods=base.periods,
        )

    _seed(db_path, [_pref("acme_CustomOpex")])
    counts = convert_pref_keys(db_path=db_path, load_set=loader)
    assert counts["converted"] == 1
    assert _keys(db_path) == {"0": "acme_CustomOpex#2"}


def test_second_run_is_idempotent(db_path: Path) -> None:
    _seed(db_path, [_pref("ResearchAndDevelopmentExpenses")])
    assert _run(db_path)["converted"] == 1
    counts = _run(db_path)
    assert counts["converted"] == 0
    assert counts["already"] == 1
    assert _keys(db_path) == {"0": "us-gaap_ResearchAndDevelopmentExpense"}


def test_ambiguous_is_skipped(db_path: Path) -> None:
    _seed(db_path, [_pref("SellingGeneralAndAdminExpenses")])
    counts = _run(db_path)
    assert counts["ambiguous"] == 1
    assert _keys(db_path) == {"0": "SellingGeneralAndAdminExpenses"}


def test_unmatched_is_skipped(db_path: Path) -> None:
    _seed(db_path, [_pref("NoSuchConcept")])
    counts = _run(db_path)
    assert counts["unmatched"] == 1
    assert _keys(db_path) == {"0": "NoSuchConcept"}


def test_conflict_is_skipped(db_path: Path) -> None:
    _seed(
        db_path,
        [
            _pref("ResearchAndDevelopmentExpenses", value=3.0),
            _pref("us-gaap_ResearchAndDevelopmentExpense", value=4.0),
        ],
    )
    counts = _run(db_path)
    assert counts["conflict"] == 1
    assert counts["already"] == 1
    assert _keys(db_path) == {
        "0": "ResearchAndDevelopmentExpenses",
        "1": "us-gaap_ResearchAndDevelopmentExpense",
    }


def test_dry_run_writes_nothing(db_path: Path) -> None:
    _seed(db_path, [_pref("ResearchAndDevelopmentExpenses")])
    counts = _run(db_path, dry_run=True)
    assert counts["converted"] == 1
    assert _keys(db_path) == {"0": "ResearchAndDevelopmentExpenses"}


def test_ticker_filter(db_path: Path) -> None:
    _seed(
        db_path,
        [
            _pref("ResearchAndDevelopmentExpenses"),
            _pref("ResearchAndDevelopmentExpenses", ticker="OTHR"),
        ],
    )
    counts = _run(db_path, tickers=["acme"])
    assert counts["converted"] == 1
    assert _keys(db_path) == {
        "0": "us-gaap_ResearchAndDevelopmentExpense",
        "1": "ResearchAndDevelopmentExpenses",
    }


def test_rename_rolls_back_on_unknown_id(db_path: Path) -> None:
    _seed(db_path, [_pref("ResearchAndDevelopmentExpenses")])
    with WizardDatabaseManager(db_path) as db, pytest.raises(KeyError):
        db.rename_adjustment_preference_keys({"0": "new_key", "99": "other"})
    assert _keys(db_path) == {"0": "ResearchAndDevelopmentExpenses"}
