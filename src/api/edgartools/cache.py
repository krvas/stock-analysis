"""LRU company cache for edgartools statement views.

Caches all statement types (income, balance, cashflow) and detail levels for a
given ``(cik, period, num_periods)`` bundle so browsing one company reuses a
single SEC fetch. Bundles are invalidated when the stored latest filing date is
more than ``EDGARTOOLS_CACHE_MAX_AGE_MONTHS`` old.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from src.config import (
    EDGARTOOLS_CACHE_DIR,
    EDGARTOOLS_CACHE_MAX_AGE_MONTHS,
    EDGARTOOLS_COMPANY_CACHE_SIZE,
)

logger = logging.getLogger(__name__)

StatementType = Literal["income", "balance", "cashflow"]
PeriodType = Literal["annual", "quarterly"]
ViewName = Literal["summary", "standard", "detailed"]
PeriodBundle = dict[StatementType, dict[ViewName, pd.DataFrame]]

_INDEX_FILENAME = "company_lru.json"
_STATEMENT_TYPES: tuple[StatementType, ...] = ("income", "balance", "cashflow")
_VIEWS: tuple[ViewName, ...] = ("summary", "standard", "detailed")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_path(cache_dir: Path) -> Path:
    return cache_dir / _INDEX_FILENAME


def _company_dir(cache_dir: Path, cik: int | str) -> Path:
    return cache_dir / "companies" / _cik_key(cik)


def _bundle_dir(
    cache_dir: Path,
    cik: int | str,
    period: PeriodType,
    num_periods: int,
) -> Path:
    return _company_dir(cache_dir, cik) / f"{period}_{num_periods}"


def _bundle_meta_path(
    cache_dir: Path,
    cik: int | str,
    period: PeriodType,
    num_periods: int,
) -> Path:
    return _bundle_dir(cache_dir, cik, period, num_periods) / "meta.json"


def _bundle_view_path(
    cache_dir: Path,
    cik: int | str,
    period: PeriodType,
    num_periods: int,
    statement_type: StatementType,
    view: ViewName,
) -> Path:
    filename = f"{statement_type}_{view}.parquet"
    return _bundle_dir(cache_dir, cik, period, num_periods) / filename


def _load_index(cache_dir: Path) -> dict[str, dict]:
    path = _index_path(cache_dir)
    if not path.exists():
        return {"companies": {}}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.warning("Corrupt edgartools LRU index at %s; starting fresh", path)
        return {"companies": {}}
    if not isinstance(data, dict) or not isinstance(data.get("companies"), dict):
        return {"companies": {}}
    return data


def _save_index(cache_dir: Path, index: dict[str, dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _index_path(cache_dir)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def _cik_key(cik: int | str) -> str:
    return str(int(cik))


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - date(year, month, 1)).days
    return date(year, month, min(value.day, last_day))


def is_period_bundle_stale(
    latest_filing_date: date,
    *,
    reference: date | None = None,
    max_age_months: int | None = None,
) -> bool:
    """Return True when ``latest_filing_date`` is more than ``max_age_months`` old."""
    reference = reference or date.today()
    max_age_months = EDGARTOOLS_CACHE_MAX_AGE_MONTHS if max_age_months is None else max_age_months
    return reference > _add_months(latest_filing_date, max_age_months)


def find_cached_cik(cache_dir: Path, ticker: str) -> str | None:
    ticker = ticker.upper()
    for cik, entry in _load_index(cache_dir)["companies"].items():
        if entry.get("ticker") == ticker:
            return cik
    return None


def delete_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    num_periods: int,
    cache_dir: Path | None = None,
) -> None:
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    bundle_dir = _bundle_dir(cache_dir, cik, period, num_periods)
    if bundle_dir.exists():
        try:
            shutil.rmtree(bundle_dir)
        except OSError as exc:
            logger.warning("Failed to delete period bundle %s: %s", bundle_dir, exc)


def load_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    num_periods: int,
    cache_dir: Path | None = None,
    reference: date | None = None,
) -> PeriodBundle | None:
    """Load a cached period bundle, or None if missing, incomplete, or stale."""
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    meta_path = _bundle_meta_path(cache_dir, cik, period, num_periods)
    if not meta_path.exists():
        return None

    try:
        with meta_path.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)
        latest_filing_date = _parse_iso_date(meta["latest_filing_date"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Invalid period bundle metadata at %s; deleting", meta_path)
        delete_period_bundle(cik=cik, period=period, num_periods=num_periods, cache_dir=cache_dir)
        return None

    if is_period_bundle_stale(latest_filing_date, reference=reference):
        logger.info(
            "Period bundle stale for CIK %s (%s, %d periods); latest filing %s",
            cik,
            period,
            num_periods,
            latest_filing_date,
        )
        delete_period_bundle(cik=cik, period=period, num_periods=num_periods, cache_dir=cache_dir)
        return None

    bundle: PeriodBundle = {}
    for statement_type in _STATEMENT_TYPES:
        views: dict[ViewName, pd.DataFrame] = {}
        for view in _VIEWS:
            path = _bundle_view_path(
                cache_dir, cik, period, num_periods, statement_type, view
            )
            if not path.exists():
                delete_period_bundle(
                    cik=cik, period=period, num_periods=num_periods, cache_dir=cache_dir
                )
                return None
            views[view] = pd.read_parquet(path)
        bundle[statement_type] = views
    return bundle


def save_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    num_periods: int,
    latest_filing_date: date,
    views: PeriodBundle,
    cache_dir: Path | None = None,
) -> None:
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    bundle_dir = _bundle_dir(cache_dir, cik, period, num_periods)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "period": period,
        "num_periods": num_periods,
        "latest_filing_date": latest_filing_date.isoformat(),
    }
    meta_path = _bundle_meta_path(cache_dir, cik, period, num_periods)
    tmp_meta = meta_path.with_suffix(".tmp")
    with tmp_meta.open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_meta.replace(meta_path)

    for statement_type in _STATEMENT_TYPES:
        statement_views = views.get(statement_type, {})
        for view in _VIEWS:
            frame = statement_views.get(view)
            if frame is None:
                continue
            frame.to_parquet(
                _bundle_view_path(cache_dir, cik, period, num_periods, statement_type, view)
            )


def _evict_company(cache_dir: Path, index: dict[str, dict], cik_key: str) -> None:
    entry = index["companies"].pop(cik_key, None)
    company_dir = _company_dir(cache_dir, cik_key)
    if company_dir.exists():
        try:
            shutil.rmtree(company_dir)
        except OSError as exc:
            logger.warning("Failed to delete cached company dir %s: %s", company_dir, exc)
    if entry:
        logger.info(
            "Evicted edgartools cache for CIK %s (%s)",
            cik_key,
            entry.get("ticker", "?"),
        )


def touch_company_cache(
    *,
    cik: int | str,
    ticker: str,
    cache_dir: Path | None = None,
    max_companies: int | None = None,
) -> list[str]:
    """Record a company fetch and evict older companies beyond ``max_companies``."""
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    limit = EDGARTOOLS_COMPANY_CACHE_SIZE if max_companies is None else max(1, max_companies)

    cik_key = _cik_key(cik)
    index = _load_index(cache_dir)
    companies = index["companies"]

    companies[cik_key] = {
        "ticker": ticker.upper(),
        "last_accessed": _utc_now_iso(),
    }

    ordered = sorted(
        companies.items(),
        key=lambda item: item[1].get("last_accessed", ""),
        reverse=True,
    )
    keep = {cik for cik, _ in ordered[:limit]}
    evicted: list[str] = []
    for other_cik in list(companies):
        if other_cik not in keep:
            _evict_company(cache_dir, index, other_cik)
            evicted.append(other_cik)

    _save_index(cache_dir, index)
    return evicted
