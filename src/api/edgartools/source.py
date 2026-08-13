"""Fetch multi-period financial statement views from edgartools."""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Literal

import pandas as pd
from dotenv import load_dotenv
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
from src.config import EDGARTOOLS_CACHE_DIR, EDGARTOOLS_COMPANY_CACHE_SIZE

StatementType = Literal["income", "balance", "cashflow"]
PeriodType = Literal["annual", "quarterly"]

_STATEMENT_TYPES: tuple[StatementType, ...] = ("income", "balance", "cashflow")
_VIEWS = ("summary", "standard", "detailed")

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

_METADATA_COLUMNS = {
    "concept",
    "label",
    "standard_concept",
    "level",
    "abstract",
    "dimension",
    "is_breakdown",
    "dimension_axis",
    "dimension_member",
    "dimension_member_label",
    "dimension_label",
    "balance",
    "weight",
    "preferred_sign",
    "parent_concept",
    "parent_abstract_concept",
}


def _configure_edgartools_cache() -> None:
    """Point edgartools at our cache directory and allow network fetches."""
    EDGARTOOLS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["EDGAR_LOCAL_DATA_DIR"] = str(EDGARTOOLS_CACHE_DIR)
    os.environ["EDGAR_ALLOW_NETWORK_FALLBACK"] = "True"

def _period_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col not in _METADATA_COLUMNS]


def _period_date(meta: dict) -> object:
    """Return the as-of date for a period (instant balance sheets use ``date``)."""
    return meta.get("end_date") or meta["date"]


def _column_for_period_date(df: pd.DataFrame, period_date) -> str | None:
    date_str = str(period_date)
    for column in _period_columns(df):
        if column.startswith(date_str):
            return column
    return None


def _row_key(row: pd.Series) -> tuple:
    return (row.get("concept"), row.get("label"))


def _is_total_row(label: object) -> bool:
    return bool(re.search(r"\btotal\b", str(label), re.IGNORECASE))


def _build_view_dataframe(
    xbrls: XBRLS,
    statement_type: StatementType,
    view: str,
    num_periods: int,
) -> pd.DataFrame:
    """Build a multi-period DataFrame with per-filing view filtering.

  XBRLS stitched ``to_dataframe()`` does not apply summary/standard/detailed
  filtering (summary and standard both map to include_dimensions=False, and the
  stitcher drops dimensional rows). We still use XBRLS for filing selection and
  period alignment, then call ``to_dataframe(view=...)`` on each underlying XBRL.
    """
    xbrl_type = _STATEMENT_XBRL_TYPES[statement_type]
    statement_getter_name = _STATEMENT_METHODS[statement_type]
    period_metas = determine_optimal_periods(
        xbrls.xbrl_list,
        xbrl_type,
        max_periods=num_periods,
    )

    if not period_metas:
        return pd.DataFrame()

    period_labels = [str(_period_date(meta)) for meta in period_metas]
    rows_by_key: dict[tuple, dict] = {}
    row_order: list[tuple] = []

    for meta in period_metas:
        xbrl = xbrls.xbrl_list[meta["xbrl_index"]]
        statement = getattr(xbrl.statements, statement_getter_name)(view=view)
        filing_df = statement.to_dataframe(view=view)
        period_date = _period_date(meta)
        period_column = _column_for_period_date(filing_df, period_date)
        period_label = str(period_date)

        for _, row in filing_df.iterrows():
            key = _row_key(row)
            if key not in rows_by_key:
                rows_by_key[key] = {
                    "label": row.get("label", ""),
                    "concept": row.get("concept"),
                    "standard_concept": row.get("standard_concept"),
                    "level": int(row.get("level", 0) or 0),
                    "is_total": _is_total_row(row.get("label", "")),
                    "values": {},
                }
                row_order.append(key)

            if period_column is not None:
                value = row.get(period_column)
                rows_by_key[key]["values"][period_label] = None if pd.isna(value) else value

    data = {
        "label": [rows_by_key[key]["label"] for key in row_order],
        "concept": [rows_by_key[key]["concept"] for key in row_order],
        "standard_concept": [rows_by_key[key]["standard_concept"] for key in row_order],
        "level": [rows_by_key[key]["level"] for key in row_order],
        "is_total": [rows_by_key[key]["is_total"] for key in row_order],
    }
    for period_label in period_labels:
        data[period_label] = [rows_by_key[key]["values"].get(period_label) for key in row_order]

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


def _build_all_statement_views(xbrls: XBRLS, num_periods: int) -> PeriodBundle:
    return {
        statement_type: {
            view: _build_view_dataframe(xbrls, statement_type, view, num_periods)
            for view in _VIEWS
        }
        for statement_type in _STATEMENT_TYPES
    }


def _load_cached_statement_views(
    *,
    cik: int | str,
    ticker: str,
    statement_type: StatementType,
    period: PeriodType,
    num_periods: int,
) -> dict[str, pd.DataFrame] | None:
    bundle = load_period_bundle(
        cik=cik,
        period=period,
        num_periods=num_periods,
        cache_dir=EDGARTOOLS_CACHE_DIR,
    )
    if bundle is None:
        return None
    touch_company_cache(
        cik=cik,
        ticker=ticker,
        cache_dir=EDGARTOOLS_CACHE_DIR,
        max_companies=EDGARTOOLS_COMPANY_CACHE_SIZE,
    )
    return bundle[statement_type]


def get_statement_views(
    ticker: str,
    statement_type: StatementType,
    period: PeriodType,
    num_periods: int = 10,
) -> dict[str, pd.DataFrame]:
    """Return summary/standard/detailed DataFrames for a stitched SEC statement."""
    load_dotenv()  # Load environment variables from .env
    if not os.environ.get("EDGAR_IDENTITY"):
        raise ValueError("EDGAR_IDENTITY environment variable is not set.")
    _configure_edgartools_cache()

    cached_cik = find_cached_cik(EDGARTOOLS_CACHE_DIR, ticker)
    if cached_cik is not None:
        cached = _load_cached_statement_views(
            cik=cached_cik,
            ticker=ticker,
            statement_type=statement_type,
            period=period,
            num_periods=num_periods,
        )
        if cached is not None:
            return cached

    company = Company(ticker)
    cached = _load_cached_statement_views(
        cik=company.cik,
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        num_periods=num_periods,
    )
    if cached is not None:
        return cached

    form = _FORM_BY_PERIOD[period]
    filings = company.get_filings(form=form, amendments=False).head(num_periods)
    latest_filing_date = _latest_filing_date(filings)
    xbrls = XBRLS.from_filings(filings, filter_amendments=True)

    all_views = _build_all_statement_views(xbrls, num_periods)

    save_period_bundle(
        cik=company.cik,
        period=period,
        num_periods=num_periods,
        latest_filing_date=latest_filing_date,
        views=all_views,
        cache_dir=EDGARTOOLS_CACHE_DIR,
    )
    touch_company_cache(
        cik=company.cik,
        ticker=ticker,
        cache_dir=EDGARTOOLS_CACHE_DIR,
        max_companies=EDGARTOOLS_COMPANY_CACHE_SIZE,
    )
    return all_views[statement_type]
