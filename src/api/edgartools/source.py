"""Fetch multi-period financial statement views from edgartools."""

from __future__ import annotations

import os
import re
from typing import Literal

from anyio import Path
import pandas as pd
from dotenv import load_dotenv
from edgar import Company, set_identity
from edgar.xbrl import XBRLS
from edgar.xbrl.stitching.periods import determine_optimal_periods

StatementType = Literal["income", "balance", "cashflow"]
PeriodType = Literal["annual", "quarterly"]

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

def _configure_edgartools_cache():
    os.environ["EDGAR_USE_LOCAL_DATA"] = "True"
    os.environ["EDGAR_LOCAL_DATA_DIR"] = str(Path(__file__).resolve().parent.parent / "data" / "edgartools_cache")

def _period_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col not in _METADATA_COLUMNS]


def _column_for_end_date(df: pd.DataFrame, end_date) -> str | None:
    end = str(end_date)
    for column in _period_columns(df):
        if column.startswith(end):
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

    period_labels = [str(meta["end_date"]) for meta in period_metas]
    rows_by_key: dict[tuple, dict] = {}
    row_order: list[tuple] = []

    for meta in period_metas:
        xbrl = xbrls.xbrl_list[meta["xbrl_index"]]
        statement = getattr(xbrl.statements, statement_getter_name)(view=view)
        filing_df = statement.to_dataframe(view=view)
        period_column = _column_for_end_date(filing_df, meta["end_date"])
        period_label = str(meta["end_date"])

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

    company = Company(ticker)
    form = _FORM_BY_PERIOD[period]
    filings = company.get_filings(form=form, amendments=False).head(num_periods)
    xbrls = XBRLS.from_filings(filings, filter_amendments=True)

    return {
        view: _build_view_dataframe(xbrls, statement_type, view, num_periods)
        for view in ("summary", "standard", "detailed")
    }
