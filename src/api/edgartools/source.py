"""Fetch multi-period financial statements from edgartools.

:func:`load_statement_set` is the entry point: it returns a
:class:`~src.models.statement.StatementSet` holding one raw detailed frame per
statement, built from up to ``MAX_CACHE_YEARS`` of filings and cached per
``(cik, period)``. Views and period windows are projections of that set.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from edgar import Company
from edgar.xbrl import XBRLS
from edgar.xbrl.stitching.periods import determine_optimal_periods

from src.api.edgartools.cache import (
    PeriodBundle,
    find_cached_cik,
    load_period_bundle,
    save_period_bundle,
    touch_company_cache,
)
from src.config import (
    EDGARTOOLS_CACHE_DIR,
    EDGARTOOLS_COMPANY_CACHE_SIZE,
    MAX_CACHE_QUARTERS,
    MAX_CACHE_YEARS,
    load_project_dotenv,
)
from src.models.statement import (
    EDGARTOOLS_METADATA_COLUMNS,
    STATEMENT_METADATA_COLUMNS,
    STATEMENT_TYPES,
    Statement,
    StatementSet,
    StatementType,
    dimension_pairs,
    format_dimension_key,
    get_row_id,
)

logger = logging.getLogger(__name__)

PeriodType = Literal["annual", "quarterly"]

__all__ = [
    "PeriodType",
    "StatementType",
    "load_statement_set",
]

_STATEMENT_METHODS: dict[StatementType, str] = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cashflow": "cash_flow_statement",
}

_STATEMENT_XBRL_TYPES: dict[StatementType, str] = {
    "income": "IncomeStatement",
    "balance": "BalanceSheet",
    "cashflow": "CashFlowStatement",
}

_FORM_BY_PERIOD: dict[PeriodType, str] = {
    "annual": "10-K",
    "quarterly": "10-Q",
}

# Max filings (and periods) cached per bundle.
_MAX_PERIODS_BY_PERIOD: dict[PeriodType, int] = {
    "annual": MAX_CACHE_YEARS,
    "quarterly": MAX_CACHE_QUARTERS,
}

# Non-metadata, non-period columns edgartools can emit (only when requested via
# include_unit / include_point_in_time); never treat them as periods.
_EDGARTOOLS_EXTRA_COLUMNS = frozenset({"unit", "point_in_time"})
_NON_PERIOD_COLUMNS = STATEMENT_METADATA_COLUMNS | _EDGARTOOLS_EXTRA_COLUMNS


def _configure_edgartools_cache() -> None:
    """Point edgartools at our cache directory and allow network fetches."""
    EDGARTOOLS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["EDGAR_LOCAL_DATA_DIR"] = str(EDGARTOOLS_CACHE_DIR)
    os.environ["EDGAR_ALLOW_NETWORK_FALLBACK"] = "True"


def _period_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col not in _NON_PERIOD_COLUMNS]


def _period_date(meta: dict) -> object:
    """Return the as-of date for a period (instant balance sheets use ``date``)."""
    return meta.get("end_date") or meta["date"]


def _column_for_period_date(df: pd.DataFrame, period_date) -> str | None:
    date_str = str(period_date)
    for column in _period_columns(df):
        if str(column).startswith(date_str):
            return column
    return None


# Metadata columns carried per row into the stored frame.
_STORED_METADATA_COLUMNS: tuple[str, ...] = (
    *EDGARTOOLS_METADATA_COLUMNS,
    "dimension_key",
    "in_standard",
)


def _empty_statement_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["row_id", *_STORED_METADATA_COLUMNS])


def _text(value: object) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def _raw_item_matches(item: dict, record: dict) -> bool:
    """Whether raw-data ``item`` is the source of ``to_dataframe`` ``record``."""
    if item.get("concept") != record.get("concept"):
        return False
    is_dimension = bool(item.get("is_dimension"))
    if is_dimension != bool(record.get("dimension")):
        return False
    if not is_dimension:
        return True
    metadata = item.get("dimension_metadata") or []
    primary = metadata[0] if metadata else {}
    return (
        _text(item.get("full_dimension_label")) == _text(record.get("dimension_label"))
        and _text(primary.get("dimension")) == _text(record.get("dimension_axis"))
        and _text(primary.get("member")) == _text(record.get("dimension_member"))
    )


def _dimension_keys(statement, frame: pd.DataFrame) -> list[str | None] | None:
    """Full ``dimension_key`` per row of ``frame`` (see ``statement.py``).

    ``to_dataframe`` exposes only the primary axis/member of a multi-axis row;
    every pair is in ``get_raw_data()``'s ``dimension_metadata``. edgartools
    builds the frame from that raw data in order, dropping only XBRL
    structural items (axes, domains, tables, root abstracts), so the frame is
    an ordered subsequence of it: match greedily, checking concept and the
    frame's own dimension columns. Returns ``None`` (caller falls back to the
    primary pair) if any frame row cannot be matched.
    """
    try:
        raw = list(statement.get_raw_data(view="detailed"))
    except Exception:  # noqa: BLE001 - edgartools raises assorted errors
        logger.warning("get_raw_data failed; using primary dimension only")
        return None

    keys: list[str | None] = []
    position = 0
    for record in frame.to_dict(orient="records"):
        while position < len(raw) and not _raw_item_matches(raw[position], record):
            position += 1
        if position == len(raw):
            logger.warning(
                "Could not align raw data with to_dataframe row %r; "
                "using primary dimension only",
                record.get("concept"),
            )
            return None
        item = raw[position]
        position += 1
        if not item.get("is_dimension"):
            keys.append(None)
            continue
        keys.append(
            format_dimension_key(
                [
                    (meta.get("dimension"), meta.get("member"))
                    for meta in item.get("dimension_metadata") or []
                ]
            )
        )
    return keys


def _standard_valid_members(xbrl, statement) -> dict[str, set[str]]:
    """Axis -> members edgartools' standard view allows for ``statement``.

    Replicates edgartools 5.47 ``XBRL.get_statement``: it resolves the
    statement's role with ``XBRL.find_statement`` and passes
    ``XBRL._get_valid_dimensional_members(presentation_tree)`` (private API —
    re-check on edgartools upgrades) to ``_generate_line_items``, which for any
    view but detailed drops dimensional facts whose member is not listed for
    their axis. Keys/members are underscore-normalised QNames. ``{}`` (no
    filtering, as in edgartools) when the role/tree cannot be resolved.
    """
    try:
        statement_id = statement.canonical_type or statement.role_or_type
        _, role, _ = xbrl.find_statement(statement_id)
        trees = xbrl.presentation_trees
        if not role or role not in trees:
            return {}
        return dict(xbrl._get_valid_dimensional_members(trees[role]))
    except Exception:  # noqa: BLE001 - edgartools raises assorted errors
        logger.warning("Could not read presentation members; in_standard unfiltered")
        return {}


def _passes_member_filter(
    pairs: list[tuple[str, str]], valid_members: dict[str, set[str]]
) -> bool:
    """edgartools' strict standard-view member check for one dimensional row.

    Mirrors the ``is_valid_dimension`` loop in edgartools 5.47
    ``XBRL._generate_line_items``: a fact is dropped if **any** of its axes is
    in ``valid_members`` with a member not listed for it; axes absent from
    ``valid_members`` never exclude. Facts of one row share all axis/member
    pairs, so the check is per row.
    """
    for axis, member in pairs:
        axis_key = str(axis).replace(":", "_")
        member_key = str(member).replace(":", "_")
        if axis_key in valid_members and member_key not in valid_members[axis_key]:
            return False
    return True


def _is_true(value: object) -> bool:
    return isinstance(value, bool | np.bool_) and bool(value)


def _in_standard(frame: pd.DataFrame, valid_members: dict[str, set[str]]) -> list:
    """Whether edgartools' ``view="standard"`` keeps each row of ``frame``.

    ``Statement._build_dataframe_from_raw_data`` keeps every non-dimensional
    item and drops dimensional items where ``is_breakdown`` (same per-item
    value as the detailed frame's column); ``get_statement`` has already
    dropped dimensional facts failing the member filter. So a row is in
    standard iff it is non-dimensional, or it is not a breakdown and passes
    :func:`_passes_member_filter` on all of its axis/member pairs.
    """
    flags = []
    for record in frame.to_dict(orient="records"):
        if not _is_true(record.get("dimension")):
            flags.append(True)
            continue
        flags.append(
            not _is_true(record.get("is_breakdown"))
            and _passes_member_filter(dimension_pairs(record), valid_members)
        )
    return flags


def _filing_frame(xbrl, statement_type: StatementType) -> pd.DataFrame | None:
    """One raw (``presentation=False``) detailed frame for one filing.

    Adds our ``dimension_key`` column (all axis/member pairs per row) and
    ``in_standard`` (edgartools' standard-view membership, see
    :func:`_in_standard`) without a second ``to_dataframe`` call.
    """
    getter = getattr(xbrl.statements, _STATEMENT_METHODS[statement_type])
    statement = getter(view="detailed")
    if statement is None:
        return None
    frame = statement.to_dataframe(view="detailed", presentation=False)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    frame = frame.copy()
    keys = _dimension_keys(statement, frame)
    frame["dimension_key"] = keys if keys is not None else None
    frame["in_standard"] = _in_standard(frame, _standard_valid_members(xbrl, statement))
    return frame


def _build_statement_dataframe(
    xbrls: XBRLS,
    statement_type: StatementType,
    max_periods: int,
) -> pd.DataFrame:
    """Build one multi-period raw detailed frame for ``statement_type``.

    XBRLS's stitched ``to_dataframe()`` drops dimensional rows, so we use XBRLS
    only for filing selection and period alignment
    (``determine_optimal_periods``, newest period first) and read each
    filing's own detailed frame, taking the column for that filing's period.

    Rows are matched across filings by :func:`get_row_id` (concept plus every
    axis/member, from ``dimension_key``), with the 1-based occurrence of that
    id within the filing (so e.g. cash beginning/end of period, which share a
    concept, stay separate rows). Metadata (including ``in_standard``) comes
    from the newest filing a row appears in (first seen wins); rows only in older
    filings are appended after it. Values keep raw XBRL signs.
    """
    period_metas = determine_optimal_periods(
        xbrls.xbrl_list,
        _STATEMENT_XBRL_TYPES[statement_type],
        max_periods=max_periods,
    )
    if not period_metas:
        return _empty_statement_frame()

    period_labels = [str(_period_date(meta)) for meta in period_metas]
    rows_by_id: dict[str, dict] = {}
    values_by_id: dict[str, dict[str, object]] = {}
    frames_by_index: dict[int, pd.DataFrame | None] = {}

    for meta, period_label in zip(period_metas, period_labels, strict=True):
        xbrl_index = meta["xbrl_index"]
        if xbrl_index not in frames_by_index:
            frames_by_index[xbrl_index] = _filing_frame(
                xbrls.xbrl_list[xbrl_index], statement_type
            )
        filing_df = frames_by_index[xbrl_index]
        if filing_df is None:
            continue
        period_column = _column_for_period_date(filing_df, _period_date(meta))

        occurrences: dict[str, int] = {}
        for record in filing_df.to_dict(orient="records"):
            if pd.isna(record.get("concept")) or not str(record["concept"]).strip():
                logger.debug("Skipping %s row without a concept", statement_type)
                continue
            base_id = get_row_id(record)
            occurrences[base_id] = occurrences.get(base_id, 0) + 1
            row_id = get_row_id(record, occurrence=occurrences[base_id])

            if row_id not in rows_by_id:
                rows_by_id[row_id] = {
                    col: record.get(col) for col in _STORED_METADATA_COLUMNS
                }
                level = record.get("level")
                rows_by_id[row_id]["level"] = 0 if pd.isna(level) else int(level)
                values_by_id[row_id] = {}

            if period_column is not None:
                value = record.get(period_column)
                values = values_by_id[row_id]
                if period_label not in values or values[period_label] is None:
                    values[period_label] = None if pd.isna(value) else value

    if not rows_by_id:
        return _empty_statement_frame()

    row_ids = list(rows_by_id)
    data: dict[str, list] = {"row_id": row_ids}
    for col in _STORED_METADATA_COLUMNS:
        data[col] = [rows_by_id[row_id][col] for row_id in row_ids]
    for period_label in dict.fromkeys(period_labels):
        # Numeric only: a stray text fact (edgartools keeps TextBlock values as
        # strings) would make the column unwritable to parquet.
        data[period_label] = pd.to_numeric(
            pd.Series(
                [values_by_id[row_id].get(period_label) for row_id in row_ids],
                dtype=object,
            ),
            errors="coerce",
        ).astype(float)
    return pd.DataFrame(data)


def _latest_filing_date(filings) -> date:
    if getattr(filings, "end_date", None):
        return date.fromisoformat(str(filings.end_date)[:10])
    filing_dates = [
        date.fromisoformat(str(getattr(filing, "filing_date", filing))[:10])
        for filing in filings
    ]
    if not filing_dates:
        raise ValueError("Cannot determine latest filing date from empty filings.")
    return max(filing_dates)


def _statement_set(bundle: PeriodBundle) -> StatementSet:
    statements = {
        statement_type: Statement(bundle[statement_type], statement_type)
        for statement_type in STATEMENT_TYPES
    }
    all_periods = {p for s in statements.values() for p in s.periods}
    return StatementSet(
        **statements,
        periods=tuple(sorted(all_periods, reverse=True)),
    )


def _touch(cik: int | str, ticker: str) -> None:
    touch_company_cache(
        cik=cik,
        ticker=ticker,
        cache_dir=EDGARTOOLS_CACHE_DIR,
        max_companies=EDGARTOOLS_COMPANY_CACHE_SIZE,
    )


def _load_cached_set(
    *, cik: int | str, ticker: str, period: PeriodType
) -> StatementSet | None:
    bundle = load_period_bundle(cik=cik, period=period, cache_dir=EDGARTOOLS_CACHE_DIR)
    if bundle is None:
        return None
    _touch(cik, ticker)
    return _statement_set(bundle)


def load_statement_set(ticker: str, period: PeriodType) -> StatementSet:
    """Return all cached periods of all three statements for ``ticker``.

    Served from the ``(cik, period)`` cache when fresh; otherwise fetches up to
    ``MAX_CACHE_YEARS`` 10-Ks (annual) or ``MAX_CACHE_QUARTERS`` 10-Qs
    (quarterly), builds, and caches the raw detailed frames.
    """
    load_project_dotenv()
    if not os.environ.get("EDGAR_IDENTITY"):
        raise ValueError("EDGAR_IDENTITY environment variable is not set.")
    _configure_edgartools_cache()

    cached_cik = find_cached_cik(EDGARTOOLS_CACHE_DIR, ticker)
    if cached_cik is not None:
        cached = _load_cached_set(cik=cached_cik, ticker=ticker, period=period)
        if cached is not None:
            return cached

    company = Company(ticker)
    cached = _load_cached_set(cik=company.cik, ticker=ticker, period=period)
    if cached is not None:
        return cached

    max_periods = _MAX_PERIODS_BY_PERIOD[period]
    filings = company.get_filings(form=_FORM_BY_PERIOD[period], amendments=False).head(
        max_periods
    )
    latest_filing_date = _latest_filing_date(filings)
    xbrls = XBRLS.from_filings(filings, filter_amendments=True)

    bundle: PeriodBundle = {}
    for statement_type in STATEMENT_TYPES:
        raw = _build_statement_dataframe(xbrls, statement_type, max_periods)
        # Statement adds tags/origin/is_total and validates row_id uniqueness.
        bundle[statement_type] = Statement(raw, statement_type).frame
    statement_set = _statement_set(bundle)

    save_period_bundle(
        cik=company.cik,
        period=period,
        latest_filing_date=latest_filing_date,
        frames=bundle,
        periods=statement_set.periods,
        cache_dir=EDGARTOOLS_CACHE_DIR,
    )
    _touch(company.cik, ticker)
    return statement_set
