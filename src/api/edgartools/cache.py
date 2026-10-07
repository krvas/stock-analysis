"""LRU company cache for edgartools statement frames.

One bundle per ``(cik, period)``: per statement type (income, balance,
cashflow) a raw detailed frame covering up to ``MAX_CACHE_YEARS`` of filings,
so any ``num_periods`` / view request is served by slicing and projecting the
same bundle, plus its per-period calc edges (``Statement.calc_edges``: each
period's calc tree from the filing its values came from). Layout::

    companies/{cik}/{period}/{statement_type}.parquet       # frame
    companies/{cik}/{period}/{statement_type}_calc.parquet  # calc edges
    companies/{cik}/{period}/meta.json   # schema_version, period,
                                         # latest_filing_date

Bundles are discarded when ``meta.json`` carries a different
:data:`CACHE_SCHEMA_VERSION` and when files are missing or unreadable. A
bundle is stale when the stored latest filing date is more than the
period-specific cache age old (:func:`read_period_bundle` reports it; the
caller rebuilds it only if SEC has a newer filing). For quarterly bundles that
date is the newer of the latest 10-Q and the latest 10-K (set by the caller),
so a bundle stays fresh after a fiscal-year 10-K.

Companies are evicted least-recently-touched first beyond
``EDGARTOOLS_COMPANY_CACHE_SIZE``. Tickers listed in the index's
``pinned_tickers`` (set with :func:`set_pinned_tickers`) are never evicted and
do not count toward that size; their bundles are still rebuilt by the
staleness/schema rules above like any other.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import (
    EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS,
    EDGARTOOLS_CACHE_DIR,
    EDGARTOOLS_COMPANY_CACHE_SIZE,
    EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS,
)
from src.models.statement import (
    STATEMENT_TYPES,
    PeriodType,
    Statement,
    StatementSet,
)

logger = logging.getLogger(__name__)

# Bump when the on-disk bundle shape (or how a stored column is computed)
# changes; mismatched bundles are rebuilt.
CACHE_SCHEMA_VERSION = 7

_INDEX_FILENAME = "company_lru.json"


@dataclass(frozen=True)
class CachedStatementSet:
    """A readable cached statement set with its ``meta.json`` freshness date."""

    statement_set: StatementSet
    # ``meta.json``'s ``latest_filing_date`` (the freshness date it was built at).
    latest_filing_date: date
    period: PeriodType
    # Date staleness is judged against (None: today).
    reference: date | None = None

    @property
    def stale(self) -> bool:
        """Whether ``latest_filing_date`` is older than the period's max cache age."""
        return is_period_bundle_stale(
            self.latest_filing_date, period=self.period, reference=self.reference
        )


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


def _bundle_file(
    cache_dir: Path, cik: int | str, period: PeriodType, name: str
) -> Path:
    return _bundle_dir(cache_dir, cik, period) / name


def _normalize_tickers(tickers: Iterable[object]) -> list[str]:
    return sorted({str(t).strip().upper() for t in tickers if str(t).strip()})


def _load_index(cache_dir: Path) -> dict[str, Any]:
    """The LRU index: ``companies`` (``{cik: entry}``) and ``pinned_tickers``.

    A missing/corrupt file yields an empty index; a missing or invalid
    ``pinned_tickers`` is treated as empty.
    """
    path = _index_path(cache_dir)
    if not path.exists():
        return {"companies": {}, "pinned_tickers": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.warning("Corrupt edgartools LRU index at %s; starting fresh", path)
        return {"companies": {}, "pinned_tickers": []}
    if not isinstance(data, dict) or not isinstance(data.get("companies"), dict):
        return {"companies": {}, "pinned_tickers": []}
    pinned = data.get("pinned_tickers")
    if not isinstance(pinned, list):
        if pinned is not None:
            logger.warning("Invalid pinned_tickers in %s; ignoring", path)
        pinned = []
    data["pinned_tickers"] = _normalize_tickers(t for t in pinned if isinstance(t, str))
    return data


def _save_index(cache_dir: Path, index: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _index_path(cache_dir)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def pinned_tickers(cache_dir: Path | None = None) -> frozenset[str]:
    """Tickers exempt from company LRU eviction (uppercased)."""
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    return frozenset(_load_index(cache_dir)["pinned_tickers"])


def set_pinned_tickers(tickers: Iterable[str], cache_dir: Path | None = None) -> None:
    """Replace the pinned-ticker list (see module doc).

    A ticker may be pinned before its company has an index entry; the pin
    takes effect once the company is touched. Pinning evicts nothing.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else EDGARTOOLS_CACHE_DIR
    index = _load_index(cache_dir)
    index["pinned_tickers"] = _normalize_tickers(tickers)
    _save_index(cache_dir, index)


def _cik_key(cik: int | str) -> str:
    return str(int(cik))


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def is_period_bundle_stale(
    latest_filing_date: date,
    *,
    period: PeriodType = "quarterly",
    reference: date | None = None,
) -> bool:
    """Return True when ``latest_filing_date`` is older than the period's max
    cache age (months, clipped to month end)."""
    reference = reference or datetime.now(UTC).date()
    max_age_months = (
        EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS
        if period == "annual"
        else EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS
    )
    expires = (
        pd.Timestamp(latest_filing_date) + pd.DateOffset(months=max_age_months)
    ).date()
    return reference > expires


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
    cache_dir: Path,
) -> None:
    bundle_dir = _bundle_dir(cache_dir, cik, period)
    if bundle_dir.exists():
        try:
            shutil.rmtree(bundle_dir)
        except OSError as exc:
            logger.warning("Failed to delete period bundle %s: %s", bundle_dir, exc)


def read_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    cache_dir: Path,
    reference: date | None = None,
    prune: bool = True,
) -> CachedStatementSet | None:
    """Load a cached bundle even if it is stale, or None (deleting it) if unusable.

    Unusable means: missing/invalid ``meta.json``, a ``schema_version`` other
    than :data:`CACHE_SCHEMA_VERSION`, or a missing/corrupt statement or
    calc-edges file. A bundle whose stored ``latest_filing_date`` is too old
    is returned with ``stale=True`` and left on disk, so the caller can check
    whether a newer filing exists before rebuilding it. ``prune=False``
    (read-only callers such as reports) returns None without deleting anything.
    """

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

    statements: dict[str, Statement] = {}
    for statement_type in STATEMENT_TYPES:
        paths = (
            _bundle_file(cache_dir, cik, period, f"{statement_type}.parquet"),
            _bundle_file(cache_dir, cik, period, f"{statement_type}_calc.parquet"),
        )
        try:
            frame, calc_edges = (pd.read_parquet(path) for path in paths)
            statements[statement_type] = Statement(
                frame, statement_type, calc_edges=calc_edges
            )
        except (OSError, ValueError) as exc:
            # FileNotFoundError, a truncated/corrupt parquet file (pyarrow's
            # ArrowInvalid subclasses ValueError), or a frame Statement rejects.
            logger.warning(
                "Unusable %s period bundle for CIK %s (%s): %s",
                statement_type,
                cik,
                period,
                exc,
            )
            discard()
            return None

    cached = CachedStatementSet(
        StatementSet(**statements), latest_filing_date, period, reference
    )
    if cached.stale:
        logger.info(
            "Period bundle stale for CIK %s (%s); latest filing %s",
            cik,
            period,
            latest_filing_date,
        )
    return cached


def save_period_bundle(
    *,
    cik: int | str,
    period: PeriodType,
    latest_filing_date: date,
    statement_set: StatementSet,
    cache_dir: Path,
) -> None:
    """Write each statement type's raw frame and calc edges plus ``meta.json``.

    ``meta.json`` is written last so a partially written bundle has no meta
    and is treated as missing.
    """
    delete_period_bundle(cik=cik, period=period, cache_dir=cache_dir)
    bundle_dir = _bundle_dir(cache_dir, cik, period)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    for statement_type in STATEMENT_TYPES:
        statement = statement_set.get(statement_type)
        statement.frame.to_parquet(
            _bundle_file(cache_dir, cik, period, f"{statement_type}.parquet")
        )
        statement.calc_edges.to_parquet(
            _bundle_file(cache_dir, cik, period, f"{statement_type}_calc.parquet")
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


def _evict_company(cache_dir: Path, index: dict[str, Any], cik_key: str) -> None:
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
) -> list[str]:
    """Record a company fetch and evict older companies beyond
    ``EDGARTOOLS_COMPANY_CACHE_SIZE``.

    Always uses ``EDGARTOOLS_CACHE_DIR`` and ``EDGARTOOLS_COMPANY_CACHE_SIZE``
    (tests override them with ``monkeypatch.setattr`` on this module).
    Pinned companies (see :func:`set_pinned_tickers`) are never evicted and
    do not count toward the size; the limit applies to the rest.
    Returns the evicted CIKs.
    """
    cache_dir = EDGARTOOLS_CACHE_DIR
    limit = EDGARTOOLS_COMPANY_CACHE_SIZE

    cik_key = _cik_key(cik)
    index = _load_index(cache_dir)
    companies = index["companies"]

    companies[cik_key] = {
        **companies.get(cik_key, {}),
        "ticker": ticker.upper(),
        "last_accessed": _utc_now_iso(),
    }

    pinned = set(index["pinned_tickers"])
    unpinned = {
        key: entry
        for key, entry in companies.items()
        if entry.get("ticker") not in pinned
    }
    ordered = sorted(
        unpinned.items(),
        key=lambda item: item[1].get("last_accessed", ""),
        reverse=True,
    )
    evicted: list[str] = []
    for other_cik, _ in ordered[limit:]:
        _evict_company(cache_dir, index, other_cik)
        evicted.append(other_cik)

    _save_index(cache_dir, index)
    return evicted
