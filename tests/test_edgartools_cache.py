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
    cached_companies,
    find_cached_cik,
    is_period_bundle_stale,
    load_period_bundle,
    save_period_bundle,
    touch_company_cache,
)
from src.models.statement import EDGARTOOLS_METADATA_COLUMNS, Statement


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
    return Statement(raw, "income").frame


def _sample_bundle() -> dict[str, pd.DataFrame]:
    return {st: _raw_frame(st) for st in ("income", "balance", "cashflow")}


def _save(cache_dir: Path, **overrides) -> None:
    kwargs = {
        "cik": 320193,
        "period": "annual",
        "latest_filing_date": date(2024, 11, 1),
        "frames": _sample_bundle(),
        "cache_dir": cache_dir,
    }
    kwargs.update(overrides)
    save_period_bundle(**kwargs)


def _load(cache_dir: Path, period: str = "annual", reference=date(2025, 1, 1)):
    return load_period_bundle(
        cik=320193, period=period, cache_dir=cache_dir, reference=reference
    )


def test_save_and_load_round_trips_raw_frames(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    bundle = _sample_bundle()
    _save(cache_dir, frames=bundle)

    bundle_dir = cache_dir / "companies" / "320193" / "annual"
    assert sorted(p.name for p in bundle_dir.iterdir()) == [
        "balance.parquet",
        "cashflow.parquet",
        "income.parquet",
        "meta.json",
    ]
    meta = json.loads((bundle_dir / "meta.json").read_text())
    assert meta == {
        "schema_version": CACHE_SCHEMA_VERSION,
        "period": "annual",
        "latest_filing_date": "2024-11-01",
    }

    loaded = _load(cache_dir)
    assert loaded is not None
    assert set(loaded) == {"income", "balance", "cashflow"}
    frame = loaded["income"]
    assert list(frame.columns) == list(bundle["income"].columns)
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
    statement = Statement(frame, "income")
    assert statement.frame["tags"].tolist() == [(), (), ()]
    assert statement.frame["row_id"].tolist() == bundle["income"]["row_id"].tolist()
    assert statement.periods == ["2024-09-28", "2023-09-30"]
    pd.testing.assert_frame_equal(
        statement.project("detailed"),
        Statement(bundle["income"], "income").project("detailed"),
    )


def test_save_requires_all_statements(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _save(tmp_path, frames={"income": _raw_frame()})


def test_load_returns_none_when_statement_file_missing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir)
    (cache_dir / "companies" / "320193" / "annual" / "balance.parquet").unlink()

    assert _load(cache_dir) is None
    assert not (cache_dir / "companies" / "320193" / "annual").exists()


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


def test_stale_bundle_is_deleted_on_load(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir, period="quarterly", latest_filing_date=date(2024, 1, 1))

    assert _load(cache_dir, period="quarterly", reference=date(2024, 4, 2)) is None
    assert not (cache_dir / "companies" / "320193" / "quarterly").exists()


def test_stale_bundle_is_kept_when_not_pruning(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    _save(cache_dir, period="quarterly", latest_filing_date=date(2024, 1, 1))

    loaded = load_period_bundle(
        cik=320193,
        period="quarterly",
        cache_dir=cache_dir,
        reference=date(2024, 4, 2),
        prune=False,
    )
    assert loaded is None
    assert (cache_dir / "companies" / "320193" / "quarterly" / "meta.json").exists()


def test_is_period_bundle_stale_respects_three_month_threshold() -> None:
    latest = date(2024, 1, 1)
    assert not is_period_bundle_stale(
        latest, reference=date(2024, 4, 1), max_age_months=3
    )
    assert is_period_bundle_stale(latest, reference=date(2024, 4, 2), max_age_months=3)


def test_default_cache_age_differs_by_period() -> None:
    latest = date(2024, 1, 1)
    assert not is_period_bundle_stale(
        latest,
        period="annual",
        reference=date(2024, 12, 1),
    )
    assert is_period_bundle_stale(
        latest,
        period="annual",
        reference=date(2025, 1, 2),
    )
    assert is_period_bundle_stale(
        latest,
        period="quarterly",
        reference=date(2024, 4, 2),
    )


def test_touch_evicts_oldest_company_directory(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    older = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    _save(cache_dir, cik=1)
    cache_mod._save_index(
        cache_dir,
        {"companies": {"1": {"ticker": "OLD", "last_accessed": older}}},
    )

    _save(cache_dir, cik=2)
    evicted = touch_company_cache(
        cik=2,
        ticker="NEW",
        cache_dir=cache_dir,
        max_companies=1,
    )

    assert evicted == ["1"]
    assert not (cache_dir / "companies" / "1").exists()
    assert (cache_dir / "companies" / "2").exists()
    assert set(_load_index(cache_dir)["companies"]) == {"2"}


def test_refetch_bumps_company_to_most_recent(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)

    for cik, ticker, when in ((1, "AAA", t0), (2, "BBB", t1)):
        _save(cache_dir, cik=cik)
        touch_company_cache(
            cik=cik, ticker=ticker, cache_dir=cache_dir, max_companies=2
        )
        index = _load_index(cache_dir)
        index["companies"][str(cik)]["last_accessed"] = when.isoformat()
        cache_mod._save_index(cache_dir, index)

    evicted = touch_company_cache(
        cik=1,
        ticker="AAA",
        cache_dir=cache_dir,
        max_companies=1,
    )

    assert evicted == ["2"]
    assert (cache_dir / "companies" / "1").exists()
    assert not (cache_dir / "companies" / "2").exists()


def test_find_cached_cik_by_ticker(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    touch_company_cache(
        cik=320193, ticker="AAPL", cache_dir=cache_dir, max_companies=10
    )

    assert find_cached_cik(cache_dir, "aapl") == "320193"
    assert find_cached_cik(cache_dir, "MSFT") is None


def test_cached_companies_lists_index(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    assert cached_companies(cache_dir) == {}
    touch_company_cache(cik=320193, ticker="aapl", cache_dir=cache_dir)
    touch_company_cache(cik=789019, ticker="MSFT", cache_dir=cache_dir)

    assert cached_companies(cache_dir) == {"320193": "AAPL", "789019": "MSFT"}
