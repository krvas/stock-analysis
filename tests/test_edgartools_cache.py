"""Unit tests for edgartools company LRU period bundle cache."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.api.edgartools import cache as cache_mod
from src.api.edgartools.cache import (
    CACHE_SCHEMA_VERSION,
    _load_index,
    find_cached_cik,
    get_cached_company_list,
    get_pinned_tickers,
    is_entry_stale,
    read_cache_entry,
    save_cache_entry,
    set_pinned_tickers,
    touch_company_cache,
)
from src.models.statement import (
    EDGARTOOLS_METADATA_COLUMNS,
    STATEMENT_TYPES,
    Statement,
    StatementSet,
)
from tests.statement_fixtures import make_statement


@pytest.fixture(autouse=True)
def _cache_dir_global(tmp_path: Path, use_cache_dir) -> None:
    """``touch_company_cache`` takes no dir: point it at the tests' cache dir."""
    use_cache_dir(tmp_path / "edgartools_cache")


def _raw_frame(label: str = "Revenue") -> pd.DataFrame:
    """A raw statement frame shaped like the source builder's output."""
    raw = pd.DataFrame(
        {
            "concept": [
                "us-gaap_RevenueAbstract",
                "us-gaap_Revenues",
                "us-gaap_Revenues",
            ],
            "label": ["Revenue:", label, f"{label} - Products"],
            "standard_concept": [None, "Revenue", "Revenue"],
            "level": [0, 1, 2],
            "abstract": [True, False, False],
            "dimension": [None, False, True],
            "is_breakdown": [None, False, True],
            "dimension_axis": [None, None, "srt_ProductOrServiceAxis"],
            "dimension_member": [None, None, "us-gaap_ProductMember"],
            "dimension_member_label": [None, None, "Products"],
            "dimension_label": [None, None, "Product or Service: Products"],
            "balance": [None, "credit", "credit"],
            "weight": [np.nan, 1.0, np.nan],
            "preferred_sign": [np.nan, -1.0, np.nan],
            "parent_concept": [None, None, "us-gaap_Revenues"],
            "parent_abstract_concept": [None, "us-gaap_RevenueAbstract", None],
            "2024-09-28": [None, 100.0, 60.0],
            "2023-09-30": [None, 90.0, None],
        }
    )
    return make_statement(raw, "income").frame


def _calc_edges() -> pd.DataFrame:
    """Per-period calc edges: the two periods' filings use different trees."""
    return pd.DataFrame(
        {
            "period": ["2024-09-28", "2023-09-30", "2023-09-30"],
            "concept": ["us-gaap_Revenues", "us-gaap_Revenues", "us-gaap_Other"],
            "parent_concept": [
                "us-gaap_GrossProfit",
                "us-gaap_NetIncomeLoss",
                "us-gaap_Revenues",
            ],
            "weight": [1.0, 1.0, -1.0],
        }
    )


def _sample_set(edges: pd.DataFrame | None = None) -> StatementSet:
    edges = _calc_edges() if edges is None else edges
    return StatementSet(
        **{
            st: Statement(_raw_frame(st), st, calc_edges=edges)
            for st in STATEMENT_TYPES
        }
    )


def _save(cache_dir: Path, **overrides) -> None:
    kwargs = {
        "cik": 320193,
        "period": "annual",
        "latest_filing_date": date(2024, 11, 1),
        "statement_set": _sample_set(),
        "cache_dir": cache_dir,
    }
    kwargs.update(overrides)
    save_cache_entry(**kwargs)


def _load(cache_dir: Path, period: str = "annual", reference=date(2025, 1, 1)):
    """The bundle if usable and fresh, else None (unusable ones are pruned)."""
    cached = read_cache_entry(
        cik=320193, period=period, cache_dir=cache_dir, reference=reference
    )
    return cached.statement_set if cached is not None and not cached.stale else None


def test_save_and_load_round_trips_raw_frames(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    statement_set = _sample_set()
    _save(cache_dir, statement_set=statement_set)

    entry_dir = cache_dir / "companies" / "320193" / "annual"
    assert sorted(p.name for p in entry_dir.iterdir()) == [
        "balance.parquet",
        "balance_calc.parquet",
        "cashflow.parquet",
        "cashflow_calc.parquet",
        "income.parquet",
        "income_calc.parquet",
        "meta.json",
    ]
    meta = json.loads((entry_dir / "meta.json").read_text())
    assert meta == {
        "schema_version": CACHE_SCHEMA_VERSION,
        "period": "annual",
        "latest_filing_date": "2024-11-01",
    }

    loaded = _load(cache_dir)
    assert loaded is not None
    assert isinstance(loaded, StatementSet)
    frame = loaded.income.frame
    assert list(frame.columns) == list(statement_set.income.frame.columns)
    for col in EDGARTOOLS_METADATA_COLUMNS:
        assert col in frame.columns

    # Mixed None/bool object columns and float metadata survive parquet.
    assert frame["abstract"].tolist() == [True, False, False]
    assert frame["dimension"].tolist() == [None, False, True]
    assert frame["is_breakdown"].tolist() == [None, False, True]
    assert pd.isna(frame["dimension_axis"].iloc[0])
    assert frame["dimension_axis"].iloc[2] == "srt_ProductOrServiceAxis"
    assert frame["preferred_sign"].iloc[1] == -1.0
    assert pd.isna(frame["preferred_sign"].iloc[0])
    assert frame["weight"].iloc[1] == 1.0

    # tags come back as numpy arrays; Statement normalizes them to tuples.
    assert frame["tags"].tolist() == [(), (), ()]
    assert frame["row_id"].tolist() == statement_set.income.frame["row_id"].tolist()
    assert loaded.income.periods == ["2024-09-28", "2023-09-30"]
    pd.testing.assert_frame_equal(
        loaded.income.project("detailed"),
        make_statement(statement_set.income.frame, "income").project("detailed"),
    )
    pd.testing.assert_frame_equal(loaded.income.calc_edges, _calc_edges())


def test_save_and_load_round_trips_empty_calc_edges(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    empty = make_statement(_raw_frame(), "income").calc_edges.iloc[0:0]
    _save(cache_dir, statement_set=_sample_set(empty))

    loaded = _load(cache_dir)
    assert loaded is not None
    edges = loaded.income.calc_edges
    assert edges.empty
    assert list(edges.columns) == ["period", "concept", "parent_concept", "weight"]


def test_schema_version_is_7() -> None:
    """Bumped for the per-period ``{statement}_calc.parquet`` files."""
    assert CACHE_SCHEMA_VERSION == 7


def test_load_returns_none_when_statement_file_missing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    (cache_dir / "companies" / "320193" / "annual" / "balance.parquet").unlink()

    assert _load(cache_dir) is None
    assert not (cache_dir / "companies" / "320193" / "annual").exists()


def test_load_returns_none_when_calc_file_missing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    (cache_dir / "companies" / "320193" / "annual" / "income_calc.parquet").unlink()

    assert _load(cache_dir) is None
    assert not (cache_dir / "companies" / "320193" / "annual").exists()


def test_load_returns_none_when_calc_file_corrupt(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    path = cache_dir / "companies" / "320193" / "annual" / "balance_calc.parquet"
    path.write_bytes(b"not parquet")

    assert _load(cache_dir) is None
    assert not path.parent.exists()


def test_load_returns_none_when_statement_file_corrupt(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    path = cache_dir / "companies" / "320193" / "annual" / "cashflow.parquet"
    path.write_bytes(b"not parquet")

    assert _load(cache_dir) is None
    assert not path.parent.exists()


@pytest.mark.parametrize("schema_version", [None, 1, CACHE_SCHEMA_VERSION + 1])
def test_schema_version_mismatch_deletes_bundle(
    tmp_path: Path, schema_version: int | None
) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    meta_path = cache_dir / "companies" / "320193" / "annual" / "meta.json"
    meta = json.loads(meta_path.read_text())
    if schema_version is None:
        del meta["schema_version"]
    else:
        meta["schema_version"] = schema_version
    meta_path.write_text(json.dumps(meta))

    assert _load(cache_dir) is None
    assert not meta_path.parent.exists()


def test_invalid_meta_deletes_bundle(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    meta_path = cache_dir / "companies" / "320193" / "annual" / "meta.json"
    meta_path.write_text("{not json")

    assert _load(cache_dir) is None
    assert not meta_path.parent.exists()


def test_periods_cached_separately(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir, period="quarterly", latest_filing_date=date(2024, 11, 1))
    assert _load(cache_dir, period="annual") is None
    assert _load(cache_dir, period="quarterly") is not None


def test_stale_bundle_is_kept_when_not_pruning(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir, period="quarterly", latest_filing_date=date(2024, 1, 1))

    cached = read_cache_entry(
        cik=320193,
        period="quarterly",
        cache_dir=cache_dir,
        reference=date(2024, 4, 2),
        prune=False,
    )
    assert cached is not None
    assert cached.stale is True
    assert (cache_dir / "companies" / "320193" / "quarterly" / "meta.json").exists()


@pytest.mark.parametrize("damage", ["meta", "corrupt", "missing"])
def test_unusable_bundle_is_kept_when_not_pruning(tmp_path: Path, damage: str) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    entry_dir = cache_dir / "companies" / "320193" / "annual"
    if damage == "meta":
        (entry_dir / "meta.json").write_text("{not json")
    elif damage == "corrupt":
        (entry_dir / "income_calc.parquet").write_bytes(b"not parquet")
    else:
        (entry_dir / "balance.parquet").unlink()

    assert (
        read_cache_entry(cik=320193, period="annual", cache_dir=cache_dir, prune=False)
        is None
    )
    assert entry_dir.exists()


def test_read_period_bundle_returns_fresh_bundle_with_filing_date(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)

    cached = read_cache_entry(
        cik=320193, period="annual", cache_dir=cache_dir, reference=date(2025, 1, 1)
    )

    assert cached is not None
    assert cached.stale is False
    assert cached.latest_filing_date == date(2024, 11, 1)
    pd.testing.assert_frame_equal(cached.statement_set.income.calc_edges, _calc_edges())


def test_read_period_bundle_keeps_and_returns_stale_bundle(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir, period="quarterly", latest_filing_date=date(2024, 1, 1))

    cached = read_cache_entry(
        cik=320193, period="quarterly", cache_dir=cache_dir, reference=date(2024, 4, 2)
    )

    assert cached is not None
    assert cached.stale is True
    assert cached.latest_filing_date == date(2024, 1, 1)
    assert cached.statement_set.income.periods == ["2024-09-28", "2023-09-30"]
    assert (cache_dir / "companies" / "320193" / "quarterly" / "meta.json").exists()


@pytest.mark.parametrize("damage", ["schema", "meta", "corrupt", "missing"])
def test_read_period_bundle_discards_unusable_stale_bundle(
    tmp_path: Path, damage: str
) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir, latest_filing_date=date(2020, 1, 1))
    entry_dir = cache_dir / "companies" / "320193" / "annual"
    if damage == "schema":
        meta = json.loads((entry_dir / "meta.json").read_text())
        meta["schema_version"] = CACHE_SCHEMA_VERSION + 1
        (entry_dir / "meta.json").write_text(json.dumps(meta))
    elif damage == "meta":
        (entry_dir / "meta.json").write_text("{not json")
    elif damage == "corrupt":
        (entry_dir / "income_calc.parquet").write_bytes(b"not parquet")
    else:
        (entry_dir / "balance.parquet").unlink()

    assert read_cache_entry(cik=320193, period="annual", cache_dir=cache_dir) is None
    assert not entry_dir.exists()


def test_is_entry_stale_respects_configured_threshold(monkeypatch) -> None:
    monkeypatch.setattr(cache_mod, "EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS", 3)
    latest = date(2024, 1, 1)
    assert not is_entry_stale(latest, reference=date(2024, 4, 1))
    assert is_entry_stale(latest, reference=date(2024, 4, 2))


def test_is_entry_stale_clips_to_month_end(monkeypatch) -> None:
    monkeypatch.setattr(cache_mod, "EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS", 1)
    latest = date(2024, 1, 31)  # + 1 month clips to 2024-02-29
    assert not is_entry_stale(latest, reference=date(2024, 2, 29))
    assert is_entry_stale(latest, reference=date(2024, 3, 1))


def test_default_cache_age_differs_by_period() -> None:
    latest = date(2024, 1, 1)
    assert not is_entry_stale(
        latest,
        period="annual",
        reference=date(2024, 12, 1),
    )
    assert is_entry_stale(
        latest,
        period="annual",
        reference=date(2025, 1, 2),
    )
    assert is_entry_stale(
        latest,
        period="quarterly",
        reference=date(2024, 4, 2),
    )


def test_touch_evicts_oldest_company_directory(tmp_path: Path, use_cache_dir) -> None:
    cache_dir = use_cache_dir(tmp_path / "edgartools_cache", 1)
    older = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    _save(cache_dir, cik=1)
    cache_mod._save_index(
        cache_dir,
        {"companies": {"1": {"ticker": "OLD", "last_accessed": older}}},
    )

    _save(cache_dir, cik=2)
    evicted = touch_company_cache(cik=2, ticker="NEW")

    assert evicted == ["1"]
    assert not (cache_dir / "companies" / "1").exists()
    assert (cache_dir / "companies" / "2").exists()
    assert set(_load_index(cache_dir)["companies"]) == {"2"}


def test_refetch_bumps_company_to_most_recent(tmp_path: Path, use_cache_dir) -> None:
    cache_dir = use_cache_dir(tmp_path / "edgartools_cache", 2)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)

    for cik, ticker, when in ((1, "AAA", t0), (2, "BBB", t1)):
        _save(cache_dir, cik=cik)
        touch_company_cache(cik=cik, ticker=ticker)
        index = _load_index(cache_dir)
        index["companies"][str(cik)]["last_accessed"] = when.isoformat()
        cache_mod._save_index(cache_dir, index)

    use_cache_dir(cache_dir, 1)
    evicted = touch_company_cache(cik=1, ticker="AAA")

    assert evicted == ["2"]
    assert (cache_dir / "companies" / "1").exists()
    assert not (cache_dir / "companies" / "2").exists()


def test_find_cached_cik_by_ticker(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    touch_company_cache(cik=320193, ticker="AAPL")

    assert find_cached_cik(cache_dir, "aapl") == "320193"
    assert find_cached_cik(cache_dir, "MSFT") is None


def test_cached_companies_lists_index(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    assert get_cached_company_list(cache_dir) == {}
    touch_company_cache(cik=320193, ticker="aapl")
    touch_company_cache(cik=789019, ticker="MSFT")

    assert get_cached_company_list(cache_dir) == {"320193": "AAPL", "789019": "MSFT"}


def _touch_at(cache_dir: Path, cik: int, ticker: str, when: datetime) -> list[str]:
    """Touch ``cik`` then backdate its ``last_accessed`` to ``when``."""
    evicted = touch_company_cache(cik=cik, ticker=ticker)
    index = _load_index(cache_dir)
    index["companies"][str(cik)]["last_accessed"] = when.isoformat()
    cache_mod._save_index(cache_dir, index)
    return evicted


def test_pinned_companies_survive_eviction_and_use_no_slots(
    tmp_path: Path, use_cache_dir
) -> None:
    cache_dir = use_cache_dir(tmp_path / "edgartools_cache", 2)
    set_pinned_tickers(["pin1", "PIN2"], cache_dir)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)

    touches = [
        (1, "PIN1"),
        (2, "PIN2"),
        (3, "AAA"),
        (4, "BBB"),
        (5, "CCC"),
    ]
    evicted: list[str] = []
    for offset, (cik, ticker) in enumerate(touches):
        _save(cache_dir, cik=cik)
        evicted += _touch_at(cache_dir, cik, ticker, t0 + timedelta(hours=offset))

    assert evicted == ["3"]
    assert set(_load_index(cache_dir)["companies"]) == {"1", "2", "4", "5"}
    for cik in (1, 2, 4, 5):
        assert (cache_dir / "companies" / str(cik)).exists()
    assert not (cache_dir / "companies" / "3").exists()


def test_set_pinned_tickers_replaces_list(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    set_pinned_tickers(["msft", "AAPL", "aapl"], cache_dir)
    assert _load_index(cache_dir)["pinned_tickers"] == ["AAPL", "MSFT"]

    set_pinned_tickers(["MU"], cache_dir)
    assert get_pinned_tickers(cache_dir) == frozenset({"MU"})


def test_pin_set_before_entry_exists_applies_on_touch(
    tmp_path: Path, use_cache_dir
) -> None:
    cache_dir = use_cache_dir(tmp_path / "edgartools_cache", 1)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    _save(cache_dir, cik=1)
    _touch_at(cache_dir, 1, "OLD", t0)

    set_pinned_tickers(["AAPL"], cache_dir)
    assert _load_index(cache_dir)["companies"].keys() == {"1"}

    _save(cache_dir, cik=320193)
    evicted = touch_company_cache(cik=320193, ticker="aapl")

    # AAPL is pinned, so OLD still fits in the single unpinned slot.
    assert evicted == []
    assert set(_load_index(cache_dir)["companies"]) == {"1", "320193"}


def test_touch_preserves_pinned_tickers(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    set_pinned_tickers(["AAPL"], cache_dir)
    touch_company_cache(cik=789019, ticker="MSFT")

    raw = json.loads((cache_dir / "company_lru.json").read_text())
    assert raw["pinned_tickers"] == ["AAPL"]
    assert set(raw["companies"]) == {"789019"}


def test_pinned_company_bundle_is_still_reported_stale(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    set_pinned_tickers(["AAPL"], cache_dir)
    _save(cache_dir, period="quarterly", latest_filing_date=date(2024, 1, 1))
    touch_company_cache(cik=320193, ticker="AAPL")

    cached = read_cache_entry(
        cik=320193, period="quarterly", cache_dir=cache_dir, reference=date(2024, 4, 2)
    )
    assert cached is not None
    assert cached.stale is True


@pytest.mark.parametrize("pinned", [None, "AAPL", {"a": 1}, ["AAPL", 3]])
def test_missing_or_invalid_pinned_tickers_tolerated(
    tmp_path: Path, pinned: object
) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    index: dict[str, object] = {"companies": {}}
    if pinned is not None:
        index["pinned_tickers"] = pinned
    cache_mod._save_index(cache_dir, index)

    expected = frozenset({"AAPL"}) if isinstance(pinned, list) else frozenset()
    assert get_pinned_tickers(cache_dir) == expected
    touch_company_cache(cik=789019, ticker="MSFT")
    assert set(_load_index(cache_dir)["companies"]) == {"789019"}
