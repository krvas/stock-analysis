"""edgartools term names used by domain code.

Two kinds of names:

- ``standard_concept`` values: edgartools' cross-company standardized labels
  (the frame's ``standard_concept`` column).
- Concept QNames: XBRL concepts as they appear in the frame's ``concept``
  column (``prefix_LocalName``), for calc-tree nodes standard labels don't cover.
"""

# --- standard_concept values -------------------------------------------------

OPERATING_EXPENSES = [
    "ResearchAndDevelopmentExpenses",
    "SellingGeneralAndAdminExpenses",
    "MarketingExpenses",
    "OtherOperatingExpense",
    "RestructuringExpenseBenefit",
    "CostsSubtotal",
    "OperatingIncomeLoss",
]

PRETAX_INCOME = "PretaxIncomeLoss"
DEPRECIATION_EXPENSE = "DepreciationExpense"

# --- concept QNames -----------------------------------------------------------

# Balance sheet: where capitalized assets and their equity offset hang
# (first one present in a period's calc tree wins).
ASSET_PARENTS = ("us-gaap_AssetsNoncurrent", "us-gaap_Assets")
EQUITY_PARENTS = (
    "us-gaap_StockholdersEquity",
    "us-gaap_StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)

# Balance sheet calc-tree roots: assets side / liabilities-and-equity side.
BALANCE_ASSETS_ROOT = "us-gaap_Assets"
BALANCE_LIABILITIES_EQUITY_ROOT = "us-gaap_LiabilitiesAndStockholdersEquity"

# Cash-flow subtotals.
CFO = "us-gaap_NetCashProvidedByUsedInOperatingActivities"
CFI = "us-gaap_NetCashProvidedByUsedInInvestingActivities"

# Working-capital change rows: presented under this header, else any concept
# whose local name starts with the prefix.
NWC_ABSTRACT = "us-gaap_IncreaseDecreaseInOperatingCapitalAbstract"
NWC_PREFIX = "IncreaseDecreaseIn"

PRETAX_LOCAL_NAME_FRAGMENT = "BeforeIncomeTax"

# Concepts reported on both the income and cash-flow statements.
NET_INCOME_CONCEPTS = ("us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss")

# D&A components reported in the notes, added to the cash-flow D&A line as
# dimensional breakdown rows on a synthetic axis (member = the note concept,
# or OTHER_DA_MEMBER for whatever the components don't explain).
COMPONENT_DA_CONCEPTS = (
    "us-gaap_Depreciation",
    "us-gaap_AmortizationOfIntangibleAssets",
    "us-gaap_FinanceLeaseRightOfUseAssetAmortization",
)
DA_COMPONENT_AXIS = "DepreciationAmortizationComponentAxis"
OTHER_DA_MEMBER = "OtherDepreciationAndAmortization"
