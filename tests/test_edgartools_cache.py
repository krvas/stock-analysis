"""Unit tests for edgartools company LRU period bundle cache."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.api.edgartools.cache import (
    _load_index,
    find_cached_cik,
    is_period_bundle_stale,
    load_period_bundle,
    save_period_bundle,
    touch_company_cache,
)


def _sample_frame(label: str = "Revenue") -> pd.DataFrame:
    return pd.DataFrame({"label": [label], "2024-09-28": [100.0]})


def _sample_bundle() -> dict[str, dict[str, pd.DataFrame]]:
    return {
        statement_type: {
            view: _sample_frame(f"{statement_type}-{view}")
            for view in ("summary", "standard", "detailed")
        }
        for statement_type in ("income", "balance", "cashflow")
    }


def test_save_and_load_period_bundle(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    bundle = _sample_bundle()

    save_period_bundle(
        cik=320193,
        period="annual",
        num_periods=10,
        latest_filing_date=date(2024, 11, 1),
        views=bundle,
        cache_dir=cache_dir,
    )

    loaded = load_period_bundle(
        cik=320193,
        period="annual",
        num_periods=10,
        cache_dir=cache_dir,
        reference=date(2025, 1, 1),
    )
    assert loaded is not None
    assert set(loaded) == {"income", "balance", "cashflow"}
    for statement_type in loaded:
        assert set(loaded[statement_type]) == {"summary", "standard", "detailed"}
        assert loaded[statement_type]["summary"].equals(bundle[statement_type]["summary"])


def test_load_returns_none_when_any_view_missing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    save_period_bundle(
        cik=320193,
        period="annual",
        num_periods=10,
        latest_filing_date=date(2024, 11, 1),
        views={
            "income": {"summary": _sample_frame()},
            "balance": {"summary": _sample_frame("Assets"), "standard": _sample_frame("Assets"), "detailed": _sample_frame("Assets")},
            "cashflow": {"summary": _sample_frame("Cash"), "standard": _sample_frame("Cash"), "detailed": _sample_frame("Cash")},
        },
        cache_dir=cache_dir,
    )

    assert (
        load_period_bundle(
            cik=320193,
            period="annual",
            num_periods=10,
            cache_dir=cache_dir,
            reference=date(2025, 1, 1),
        )
        is None
    )
    assert not (cache_dir / "companies" / "320193" / "annual_10").exists()


def test_stale_bundle_is_deleted_on_load(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    save_period_bundle(
        cik=320193,
        period="quarterly",
        num_periods=10,
        latest_filing_date=date(2024, 1, 1),
        views=_sample_bundle(),
        cache_dir=cache_dir,
    )

    loaded = load_period_bundle(
        cik=320193,
        period="quarterly",
        num_periods=10,
        cache_dir=cache_dir,
        reference=date(2024, 4, 2),
    )
    assert loaded is None
    assert not (cache_dir / "companies" / "320193" / "quarterly_10").exists()


def test_is_period_bundle_stale_respects_three_month_threshold() -> None:
    latest = date(2024, 1, 1)
    assert not is_period_bundle_stale(latest, reference=date(2024, 4, 1), max_age_months=3)
    assert is_period_bundle_stale(latest, reference=date(2024, 4, 2), max_age_months=3)


def test_touch_evicts_oldest_company_directory(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    older = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    save_period_bundle(
        cik=1,
        period="annual",
        num_periods=1,
        latest_filing_date=date(2024, 11, 1),
        views=_sample_bundle(),
        cache_dir=cache_dir,
    )
    from src.api.edgartools import cache as cache_mod

    cache_mod._save_index(
        cache_dir,
        {"companies": {"1": {"ticker": "OLD", "last_accessed": older}}},
    )

    save_period_bundle(
        cik=2,
        period="annual",
        num_periods=1,
        latest_filing_date=date(2024, 11, 1),
        views=_sample_bundle(),
        cache_dir=cache_dir,
    )
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
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)

    for cik, ticker, when in ((1, "AAA", t0), (2, "BBB", t1)):
        save_period_bundle(
            cik=cik,
            period="annual",
            num_periods=1,
            latest_filing_date=date(2024, 11, 1),
            views=_sample_bundle(),
            cache_dir=cache_dir,
        )
        touch_company_cache(cik=cik, ticker=ticker, cache_dir=cache_dir, max_companies=2)
        index = _load_index(cache_dir)
        index["companies"][str(cik)]["last_accessed"] = when.isoformat()
        from src.api.edgartools import cache as cache_mod

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
    touch_company_cache(cik=320193, ticker="AAPL", cache_dir=cache_dir, max_companies=10)

    assert find_cached_cik(cache_dir, "aapl") == "320193"
    assert find_cached_cik(cache_dir, "MSFT") is None


def test_balance_sheet_served_from_income_bundle(tmp_path: Path) -> None:
    cache_dir = tmp_path / "edgartools_cache"
    bundle = _sample_bundle()
    save_period_bundle(
        cik=320193,
        period="quarterly",
        num_periods=10,
        latest_filing_date=date(2024, 11, 1),
        views=bundle,
        cache_dir=cache_dir,
    )

    loaded = load_period_bundle(
        cik=320193,
        period="quarterly",
        num_periods=10,
        cache_dir=cache_dir,
        reference=date(2025, 1, 1),
    )
    assert loaded is not None
    assert loaded["balance"]["summary"].equals(bundle["balance"]["summary"])
