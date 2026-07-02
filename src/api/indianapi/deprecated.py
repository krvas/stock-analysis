"""
Included just in case there was some issue in refactoring these dictionaries to JSON files. These are now deprecated and should not be used in the codebase.
"""


from typing import Final


API_NAME_BY_SYMBOL: Final[dict[str, str]] = {
    "TCS": "TCS",
    "SUNPHARMA": "Sun Pharmaceutical",
    "SBILIFE": "SBI Life",
    "RELIANCE": "Reliance Industries",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "BAJFINANCE": "Bajaj Finance",
    "INFY": "Infosys",
    "HINDUNILVR": "Hindustan Unilever",
    "TATASTEEL": "Tata Steel",
    "TATAMOTORS": "Tata Motors",
    "TMCV": "Tata Motors",
    "DLF": "DLF",
    "BHARTIARTL": "Bharti Airtel",
    "NTPC": "NTPC",
}

INC_FIELD_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "revenue": ("TotalRevenue", "Revenue", "InterestIncomeBank"),
    "cost_of_revenue": ("CostofRevenueTotal",),
    "gross_profit": ("GrossProfit",),
    "operating_expenses": ("TotalOperatingExpense", "Non-InterestExpenseBank"),
    "operating_profit": ("OperatingIncome", "NetInterestIncAfterLoanLossProv"),
    "interest_expense": ("TotalInterestExpense", "InterestInc(Exp)Net-Non-OpTotal"),
    "profit_before_tax": ("NetIncomeBeforeTaxes",),
    "tax_expense": ("ProvisionforIncomeTaxes",),
    "net_profit": ("NetIncome",),
    "eps_diluted": ("DilutedEPSExcludingExtraOrdItems", "DilutedNormalizedEPS"),
}

BAL_FIELD_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "total_assets": ("TotalAssets",),
    "current_assets": ("TotalCurrentAssets",),
    "cash_and_equivalents": (
        "CashandShortTermInvestments",
        "Cash",
        "CashEquivalents",
    ),
    "inventory": ("TotalInventory",),
    "receivables": ("TotalReceivablesNet", "AccountsReceivable-TradeNet"),
    "total_liabilities": ("TotalLiabilities",),
    "current_liabilities": ("TotalCurrentLiabilities",),
    "total_debt": ("TotalDebt",),
    "short_term_debt": ("NotesPayable/ShortTermDebt", "TotalShortTermBorrowings"),
    "long_term_debt": ("LongTermDebt", "TotalLongTermDebt"),
    "total_equity": ("TotalEquity",),
    "retained_earnings": ("RetainedEarnings(AccumulatedDeficit)",),
}

CAS_FIELD_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "operating_cash_flow": ("CashfromOperatingActivities",),
    "investing_cash_flow": ("CashfromInvestingActivities",),
    "financing_cash_flow": ("CashfromFinancingActivities",),
    "net_cash_flow": ("NetChangeinCash",),
    "capex": ("CapitalExpenditures",),
}