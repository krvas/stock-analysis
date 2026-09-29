"""LRU company cache for edgartools statement frames.

One bundle per ``(cik, period)``: a raw detailed frame per statement type
(income, balance, cashflow) covering up to ``MAX_CACHE_YEARS`` of filings, so
any ``num_periods`` / view request is served by slicing and projecting the same
bundle. Layout::

    companies/{cik}/{period}/{statement_type}.parquet
    companies/{cik}/{period}/meta.json   # schema_version, period,
                                         # latest_filing_date

Bundles are rebuilt when ``meta.json`` carries a different
:data:`CACHE_SCHEMA_VERSION`, when files are missing or unreadable, and when
the stored latest filing date is more than the period-specific cache age old.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from src.config import (
    EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS,
    EDGARTOOLS_CACHE_DIR,
    EDGARTOOLS_COMPANY_CACHE_SIZE,
    EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS,
)
from src.models.statement import STATEMENT_TYPES, StatementType

logger = logging.getLogger(__name__)

PeriodType = Literal["annual", "quarterly"]
# Raw (unprojected, raw-sign) statement frame per statement type.
PeriodBundle = dict[StatementType, pd.DataFrame]

# Bump when the on-disk bundle shape changes; mismatched bundles are rebuilt.
CACHE_SCHEMA_VERSION = 4

_INDEX_FILENAME = "company_lru.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _index_path(cache_dir: Path) -> Path:
    return cache_dir / _INDEX_FILENAME


def _company_dir(cache_dir: Path, cik: int | str) -> Path:
    return cache_dir / "companies" / _cik_key(cik)


def _bundle_dir(cache_dir: Path, cik: int | str, period: PeriodType) -> Path:
    return _company_dir(cache_dir, cik) / period


def _bundle_meta_path(cache_dir: Path, cik: int | str, period: PeriodType) -> Path:
    return _bundle_dir(cache_dir, cik, period) / "meta.json"


def _bundle_statement_path(
    cache_dir: Path,
    cik: int | str,
    period: PeriodType,
    statement_type: StatementType,
) -> Path:
    return _bundle_dir(cache_dir, cik, period) / f"{statement_type}.parquet"


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
    period: PeriodType = "quarterly",
    reference: date | None = None,
    max_age_months: int | None = None,
) -> bool:
    """Return True when ``latest_filing_date`` is more than ``max_age_months`` old."""
    reference = reference or datetime.now(UTC).date()
    if max_age_months is None:
        max_age_months = (
            EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS
            if period == "annual"
            else EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS
        )
    return reference > _add_months(latest_filing_date, max_age_months)


def cached_companies(cache_dir: Path) -> dict[str, str]:
    """``{cik: ticker}`` for every company in the LRU index (index only; bundles
    may still be missing or stale)."""
    return {
        cik: entry["ticker"]
        for cik, entry in _load_index(cache_dir)["companies"].items()
        if entry.get("ticker")
    }


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
    cache_dir: Path | None = None,
) -> None:
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    bundle_dir = _bundle_dir(cache_dir, cik, period)
    if bundle_dir.exists():
        try:
            shutil.rmtree(bundle_dir)
        except OSError as exc:
            logger.warning("Failed to delete period bundle %s: %s", bundle_dir, exc)


def load_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    cache_dir: Path | None = None,
    reference: date | None = None,
    prune: bool = True,
) -> PeriodBundle | None:
    """Load a cached bundle, or None (deleting it) if unusable.

    Unusable means: missing/invalid ``meta.json``, a ``schema_version`` other
    than :data:`CACHE_SCHEMA_VERSION`, stale, or a missing/corrupt statement
    file. ``prune=False`` (read-only callers such as reports) returns None
    without deleting anything.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR

    def discard() -> None:
        if prune:
            delete_period_bundle(cik=cik, period=period, cache_dir=cache_dir)

    meta_path = _bundle_meta_path(cache_dir, cik, period)
    if not meta_path.exists():
        if _bundle_dir(cache_dir, cik, period).exists():
            discard()
        return None

    try:
        with meta_path.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)
        schema_version = meta.get("schema_version")
        latest_filing_date = _parse_iso_date(meta["latest_filing_date"])
    except (OSError, json.JSONDecodeError, AttributeError, KeyError, ValueError):
        logger.warning("Invalid period bundle metadata at %s", meta_path)
        discard()
        return None

    if schema_version != CACHE_SCHEMA_VERSION:
        logger.info(
            "Period bundle for CIK %s (%s) has schema_version %r (want %d)",
            cik,
            period,
            schema_version,
            CACHE_SCHEMA_VERSION,
        )
        discard()
        return None

    if is_period_bundle_stale(latest_filing_date, period=period, reference=reference):
        logger.info(
            "Period bundle stale for CIK %s (%s); latest filing %s",
            cik,
            period,
            latest_filing_date,
        )
        discard()
        return None

    bundle: PeriodBundle = {}
    for statement_type in STATEMENT_TYPES:
        path = _bundle_statement_path(cache_dir, cik, period, statement_type)
        try:
            bundle[statement_type] = pd.read_parquet(path)
        except (OSError, ValueError) as exc:
            # FileNotFoundError, or a truncated/corrupt parquet file
            # (pyarrow's ArrowInvalid subclasses ValueError).
            logger.warning("Unreadable period bundle file %s (%s)", path, exc)
            discard()
            return None
    return bundle


def save_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    latest_filing_date: date,
    frames: Mapping[StatementType, pd.DataFrame],
    cache_dir: Path | None = None,
) -> None:
    """Write one raw frame per statement type plus ``meta.json``.

    ``meta.json`` is written last so a partially written bundle has no meta
    and is treated as missing.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    missing = [st for st in STATEMENT_TYPES if st not in frames]
    if missing:
        raise ValueError(f"period bundle is missing statement(s): {missing}")

    delete_period_bundle(cik=cik, period=period, cache_dir=cache_dir)
    bundle_dir = _bundle_dir(cache_dir, cik, period)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    for statement_type in STATEMENT_TYPES:
        frames[statement_type].to_parquet(
            _bundle_statement_path(cache_dir, cik, period, statement_type)
        )

    meta = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "period": period,
        "latest_filing_date": latest_filing_date.isoformat(),
    }
    meta_path = _bundle_meta_path(cache_dir, cik, period)
    tmp_meta = meta_path.with_suffix(".tmp")
    with tmp_meta.open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_meta.replace(meta_path)


def _evict_company(cache_dir: Path, index: dict[str, dict], cik_key: str) -> None:
    entry = index["companies"].pop(cik_key, None)
    company_dir = _company_dir(cache_dir, cik_key)
    if company_dir.exists():
        try:
            shutil.rmtree(company_dir)
        except OSError as exc:
            logger.warning(
                "Failed to delete cached company dir %s: %s", company_dir, exc
            )
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
    limit = (
        EDGARTOOLS_COMPANY_CACHE_SIZE
        if max_companies is None
        else max(1, max_companies)
    )

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
