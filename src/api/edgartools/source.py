"""Fetch multi-period financial statements from edgartools.

:func:`load_statement_set` is the entry point: it returns a
:class:`~src.models.statement.StatementSet` holding one raw detailed frame per
statement, built from up to ``MAX_CACHE_YEARS`` of filings and cached per
``(cik, period)``. Views and period windows are projections of that set.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from datetime import date
from typing import Literal

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
    format_dimension_key,
    get_row_id,
)

logger = logging.getLogger(__name__)

PeriodType = Literal["annual", "quarterly"]

__all__ = [
    "FORM_BY_PERIOD",
    "MAX_PERIODS_BY_PERIOD",
    "PeriodType",
    "StatementType",
    "load_statement_set",
    "setup_edgartools",
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

FORM_BY_PERIOD: dict[PeriodType, str] = {
    "annual": "10-K",
    "quarterly": "10-Q",
}

# Max filings (and periods) cached per bundle.
MAX_PERIODS_BY_PERIOD: dict[PeriodType, int] = {
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


def setup_edgartools() -> None:
    """Load ``.env``, require ``EDGAR_IDENTITY`` and configure the cache.

    Call before any edgartools network access.
    """
    load_project_dotenv()
    if not os.environ.get("EDGAR_IDENTITY"):
        raise ValueError("EDGAR_IDENTITY environment variable is not set.")
    _configure_edgartools_cache()


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


def _align[T, U](
    sub_records: Sequence[T],
    super_records: Sequence[U],
    matches: Callable[[T, U], bool],
) -> list[int] | None:
    """Positions in ``super_records`` of each of ``sub_records``.

    ``sub_records`` must be an ordered subsequence of ``super_records`` (the
    same walk with some items dropped): each sub record is matched greedily to
    the next super record for which ``matches(sub, super)`` holds. Returns
    ``None`` if any sub record cannot be matched.
    """
    positions: list[int] = []
    position = 0
    for record in sub_records:
        while position < len(super_records) and not matches(
            record, super_records[position]
        ):
            position += 1
        if position == len(super_records):
            return None
        positions.append(position)
        position += 1
    return positions


def _raw_items(statement, frame: pd.DataFrame) -> list[dict] | None:
    """The ``get_raw_data(view="detailed")`` item behind each row of ``frame``.

    edgartools builds the frame from that raw data in order, dropping only
    XBRL structural items (axes, domains, tables, root abstracts), so the frame
    is an ordered subsequence of it (:func:`_align`, checking concept and the
    frame's own dimension columns). Returns ``None`` on an edgartools error or
    if any frame row cannot be matched; callers keep the frame's own values.
    """
    try:
        raw = list(statement.get_raw_data(view="detailed"))
    except Exception:  # noqa: BLE001 - edgartools raises assorted errors
        logger.warning(
            "get_raw_data failed; using primary dimension and edgartools' weight"
        )
        return None

    positions = _align(
        frame.to_dict(orient="records"),
        raw,
        lambda record, item: _raw_item_matches(item, record),
    )
    if positions is None:
        logger.warning(
            "Could not align raw data with to_dataframe rows; "
            "using primary dimension and edgartools' weight"
        )
        return None
    return [raw[position] for position in positions]


def _dimension_key(item: dict) -> str | None:
    """Full ``dimension_key`` of a raw item (see ``statement.py``).

    ``to_dataframe`` exposes only the primary axis/member of a multi-axis row;
    every pair is in the raw item's ``dimension_metadata``.
    """
    if not item.get("is_dimension"):
        return None
    return format_dimension_key(
        [
            (meta.get("dimension"), meta.get("member"))
            for meta in item.get("dimension_metadata") or []
        ]
    )


def _role_weights(frame: pd.DataFrame, items: Sequence[dict]) -> pd.Series:
    """Calc ``weight`` per row of ``frame`` from this statement's own role.

    ``to_dataframe`` fills ``weight`` from the concept's first fact, whose
    weight can come from a different role's calc tree than the frame's
    ``parent_concept`` (e.g. +1 from the income role for a concept that is −1
    under the cash-flow role). Non-dimensional raw items carry the weight from
    the same calc node as their ``calculation_parent`` (the frame's
    ``parent_concept``). Dimensional raw items carry no weight; edgartools
    treats weight and ``parent_concept`` as concept attributes, so they take
    their concept's role weight. Rows whose concept has no raw weight keep the
    frame's.
    """
    by_concept: dict[object, object] = {}
    for item in items:
        weight = item.get("weight")
        if item.get("is_dimension") or weight is None or pd.isna(weight):
            continue
        by_concept.setdefault(item.get("concept"), weight)
    role = pd.to_numeric(frame["concept"].map(by_concept), errors="coerce")
    return role.where(role.notna(), frame["weight"])


# Columns identifying one ``to_dataframe`` row across views of one filing.
_ROW_MATCH_COLUMNS: tuple[str, ...] = (
    "concept",
    "label",
    "dimension",
    "dimension_axis",
    "dimension_member",
    "dimension_label",
)


def _rows_match(left: dict, right: dict) -> bool:
    return all(_text(left.get(c)) == _text(right.get(c)) for c in _ROW_MATCH_COLUMNS)


def _in_standard(statement, frame: pd.DataFrame) -> list[bool] | list[None]:
    """Whether edgartools' ``view="standard"`` keeps each row of ``frame``.

    ``to_dataframe(view="standard")`` walks the same presentation tree as the
    detailed frame and only drops rows (breakdown dimensions and dimensional
    facts whose member is not in the presentation linkbase), so its rows are
    an ordered subsequence of ``frame``'s: rows :func:`_align` matches are in
    standard, the rest are not. On an edgartools error or failed alignment
    every flag is ``None`` and :class:`~src.models.statement.Statement` fills
    its default.
    """
    unknown: list[None] = [None] * len(frame)
    try:
        standard = statement.to_dataframe(view="standard", presentation=False)
    except Exception:  # noqa: BLE001 - edgartools raises assorted errors
        logger.warning("Standard to_dataframe failed; in_standard left to default")
        return unknown
    if not isinstance(standard, pd.DataFrame) or standard.empty:
        logger.warning("Standard to_dataframe returned no rows; default in_standard")
        return unknown

    positions = _align(
        standard.to_dict(orient="records"),
        frame.to_dict(orient="records"),
        _rows_match,
    )
    if positions is None:
        logger.warning(
            "Could not align standard rows with detailed rows; "
            "in_standard left to default"
        )
        return unknown
    flags = [False] * len(frame)
    for position in positions:
        flags[position] = True
    return flags


def _filing_frame(xbrl, statement_type: StatementType) -> pd.DataFrame | None:
    """One raw (``presentation=False``) detailed frame for one filing.

    Adds our ``dimension_key`` column (all axis/member pairs per row) and
    ``in_standard`` (edgartools' own ``view="standard"`` membership, see
    :func:`_in_standard`), and replaces ``weight`` with this statement role's
    calc weight (:func:`_role_weights`). Raw data is fetched and aligned once
    (:func:`_raw_items`); if that fails, ``dimension_key`` falls back to the
    primary pair and ``weight`` stays edgartools'.
    """
    getter = getattr(xbrl.statements, _STATEMENT_METHODS[statement_type])
    statement = getter(view="detailed")
    if statement is None:
        return None
    frame = statement.to_dataframe(view="detailed", presentation=False)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    frame = frame.copy()
    items = _raw_items(statement, frame)
    if items is None:
        frame["dimension_key"] = None
    else:
        frame["dimension_key"] = [_dimension_key(item) for item in items]
        frame["weight"] = _role_weights(frame, items)
    frame["in_standard"] = _in_standard(statement, frame)
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
    from the newest filing a row appears in (first seen wins), except
    ``weight``, which is the newest non-NaN weight across filings (a filing
    can list a calc child without a weight); rows only in older filings are
    appended after it. Values keep raw XBRL signs.
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
            elif pd.isna(rows_by_id[row_id]["weight"]):
                # A newer filing may omit the calc weight (NaN); take the
                # newest known one rather than leaving it unknown.
                rows_by_id[row_id]["weight"] = record.get("weight")

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
    for period_label in period_labels:
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
    setup_edgartools()

    cached_cik = find_cached_cik(EDGARTOOLS_CACHE_DIR, ticker)
    if cached_cik is not None:
        cached = _load_cached_set(cik=cached_cik, ticker=ticker, period=period)
        if cached is not None:
            return cached

    company = Company(ticker)
    cached = _load_cached_set(cik=company.cik, ticker=ticker, period=period)
    if cached is not None:
        return cached

    max_periods = MAX_PERIODS_BY_PERIOD[period]
    filings = company.get_filings(form=FORM_BY_PERIOD[period], amendments=False).head(
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
        cache_dir=EDGARTOOLS_CACHE_DIR,
    )
    _touch(company.cik, ticker)
    return statement_set
