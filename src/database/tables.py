"""Table names and column definitions aligned with schema.sql."""

from __future__ import annotations

from typing import Final

# Table names
COMPANIES: Final[str] = "companies"
PRICES: Final[str] = "prices"
FINANCIALS: Final[str] = "financials"
BALANCE_SHEETS: Final[str] = "balance_sheets"
CASH_FLOWS: Final[str] = "cash_flows"
CORPORATE_ACTIONS: Final[str] = "corporate_actions"

ALL_TABLES: Final[tuple[str, ...]] = (
    COMPANIES,
    PRICES,
    FINANCIALS,
    BALANCE_SHEETS,
    CASH_FLOWS,
    CORPORATE_ACTIONS,
)

# Primary key columns per table (used for upserts)
PRIMARY_KEYS: Final[dict[str, tuple[str, ...]]] = {
    COMPANIES: ("company_id",),
    PRICES: ("company_id", "trade_date"),
    FINANCIALS: ("company_id", "period_end_date", "period_type"),
    BALANCE_SHEETS: ("company_id", "period_end_date", "period_type"),
    CASH_FLOWS: ("company_id", "period_end_date", "period_type"),
    CORPORATE_ACTIONS: ("company_id", "action_date", "action_type"),
}

# Writable columns (excludes DEFAULT-generated timestamps where noted)
TABLE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    COMPANIES: (
        "company_id",
        "symbol",
        "exchange",
        "country",
        "isin",
        "company_name",
        "sector",
        "industry",
        "shares_outstanding",
        "shares_diluted",
        "listing_date",
        "is_active",
        "source",
        "created_at",
        "updated_at",
    ),
    PRICES: (
        "company_id",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adj_close",
        "source",
        "ingested_at",
    ),
    FINANCIALS: (
        "company_id",
        "period_end_date",
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "currency",
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_expenses",
        "operating_profit",
        "ebitda",
        "ebit",
        "interest_expense",
        "profit_before_tax",
        "tax_expense",
        "net_profit",
        "eps_basic",
        "eps_diluted",
        "source",
        "ingested_at",
    ),
    BALANCE_SHEETS: (
        "company_id",
        "period_end_date",
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "currency",
        "total_assets",
        "current_assets",
        "non_current_assets",
        "cash_and_equivalents",
        "inventory",
        "receivables",
        "total_liabilities",
        "current_liabilities",
        "non_current_liabilities",
        "total_debt",
        "short_term_debt",
        "long_term_debt",
        "total_equity",
        "retained_earnings",
        "source",
        "ingested_at",
    ),
    CASH_FLOWS: (
        "company_id",
        "period_end_date",
        "period_type",
        "fiscal_year",
        "fiscal_quarter",
        "currency",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
        "capex",
        "free_cash_flow",
        "source",
        "ingested_at",
    ),
    CORPORATE_ACTIONS: (
        "company_id",
        "action_date",
        "action_type",
        "ex_date",
        "record_date",
        "payment_date",
        "currency",
        "amount",
        "ratio_from",
        "ratio_to",
        "description",
        "source",
        "ingested_at",
    ),
}

# Column defaults from schema.sql (applied when upsert omits NOT NULL columns)
SCHEMA_DEFAULTS: Final[dict[str, dict[str, object]]] = {
    COMPANIES: {"is_active": True, "source": "finfetch"},
    PRICES: {"source": "finfetch"},
    FINANCIALS: {"currency": "INR", "source": "finfetch"},
    BALANCE_SHEETS: {"currency": "INR", "source": "finfetch"},
    CASH_FLOWS: {"currency": "INR", "source": "finfetch"},
    CORPORATE_ACTIONS: {"currency": "INR", "source": "finfetch"},
}
