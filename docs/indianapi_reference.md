# Indian API Reference — NSE / BSE Equities

Investigation date: 2026-06-30  
Base URL: **`https://stock.indianapi.in`**  
Auth: **`x-api-key`** header (key in `.env` as `INDIAN_API_KEY`)  
Free tier: **500 requests/month** — **~92 used** during this investigation (~408 remaining)

Sample tickers: 15 names chosen to stress-test banks/NBFC/insurance vs industrials (see ticker table below).

This document records actual return shapes from [IndianAPI.in](https://indianapi.in/indian-stock-market) and maps them to our DuckDB schema (`src/database/schema.sql`). Use this instead of re-discovering field availability during wrapper and ingestion work.

Probe artifacts: `scripts/investigate_indianapi.py`, `scripts/indianapi_probe_output.json`

---

## Step 1 — Indian API Return Shapes

### General conventions

| Aspect | Actual behavior |
|--------|-----------------|
| Base URL | `https://stock.indianapi.in` (not `indianapi.in/api/...`) |
| Auth | `x-api-key: <key>` on every request |
| Company lookup (`/stock`) | **Name-based search**, not ticker/ISIN. Param: `name` (string). Fragile — see [Name matching](#name-matching-strategy). |
| Price history (`/historical_data`) | Param: **`stock_name`** (company name string). `symbol` / `name` return **422**. |
| Financial statements (`/stock`) | `financials` is a **`list[dict]`** — one dict per fiscal period. Duplicate mirror: `stockFinancialData` (same shape). |
| Statement line items | Nested under `stockFinancialMap` → **`INC`** (income), **`BAL`** (balance), **`CAS`** (cash flow). Each is `list[{displayName, key, value, qoQComp, yqoQComp}]`. |
| Monetary `value` | **Always a string** when present (e.g. `"81511.14"`, `"-48195.19"`). Parse with `float()`. |
| Value units | **INR crores** (validated: Bajaj Finance `TotalRevenue` = `54969.49` matches FY24 revenue ~₹54,969 cr). |
| Period granularity | **`Type: "Annual"`** and **`Type: "Interim"`** in the same list. Interim = quarterly. |
| Period metadata | `EndDate`, `FiscalYear`, `StatementDate`, `Type`, `fiscalPeriodNumber` on each period object. **`fiscalPeriodNumber` is always `0`** — do not use for quarter detection. |
| Embedded metadata rows | `periodType` / `periodLength` appear as **fake line items** inside `INC`/`BAL`/`CAS` (`value` = `"Months"` / `"12"`). **Skip when mapping.** |
| Nulls | Missing line item → key absent from array. Present row with unknown amount → not observed; `value` null not seen on monetary rows. `qoQComp` / `yqoQComp` are usually `null`. |
| API null stripping | Docs state null keys are removed from responses. |

---

### Endpoints in scope

| Endpoint | Params (observed) | Purpose |
|----------|-------------------|---------|
| `GET /stock` | `name` | Company profile + bundled financials |
| `GET /historical_data` | `stock_name`, `period`, `filter` | Daily price + volume (+ DMAs with `filter=price`) |
| `GET /corporate_actions` | `stock_name` | Dividends, splits, bonus, rights, board meetings |
| `GET /statement` | *(not probed — budget preserved)* | Documented in OpenAPI; likely overlaps `/stock` financials |
| `GET /historical_stats` | `stock_name`, `stats` | Tabular financials (fallback for insurance — see gaps) |

**Out of scope** (per project brief): `/news`, `/ipo`, `/trending`, `/commodities`, `/mutual_funds`, `/price_shockers`, `/BSE_most_active`, `/NSE_most_active`, `/stock_forecasts`, `/stock_target_price`, `/recent_announcements`.

---

### `GET /stock` — company profile + financials bundle

**Return type:** `dict` (or `{"error": "Stock not found"}` on failed name match)

**Top-level keys (typical success response):**

`companyName`, `industry`, `companyProfile`, `currentPrice`, `financials`, `stockFinancialData`, `keyMetrics`, `shareholding`, `analystView`, `stockTechnicalData`, `stockDetailsReusableData`, `percentChange`, `yearHigh`, `yearLow`, `recentNews`, …

**`companyProfile` — master data fields observed:**

| Field | Type | Sample (HDFC Bank) | Notes |
|-------|------|--------------------|-------|
| `exchangeCodeNse` | `str` | `"HDFCBANK"` | Preferred for `companies.symbol` when present |
| `exchangeCodeBse` | `str` | `"500180"` | BSE numeric code |
| `isInId` | `str` | `"INE040A01034"` | Maps to `companies.isin` |
| `mgIndustry` | `str` | `"Regional Banks"` | Fallback for `industry` |
| `mgSector` | `str` | usually `null` | Fallback for `sector` |
| `companyDescription` | `str` | long text | Not in schema |
| `officers` | `list` | management list | Not in schema |
| `peerCompanyList` | `list[dict]` | peer comps with ratios | Not in schema — future table candidate |

**Not present in `companyProfile` for probed tickers:** `listingDate`, `sharesOutstanding`, `tickerId`, `commonName`, `mgSector` (usually null).

**`currentPrice`:** `{"BSE": "798.40", "NSE": "797.95"}` — strings, not floats.

---

### `financials` / `stockFinancialData` — statement periods

**Return type:** `list[dict]` (or `null` for SBI Life)

**Period object shape:**

```json
{
  "EndDate": "2025-03-31",
  "FiscalYear": "2025",
  "StatementDate": "2026-03-31",
  "Type": "Annual",
  "fiscalPeriodNumber": 0,
  "stockFinancialMap": {
    "INC": [ { "displayName": "...", "key": "TotalRevenue", "value": "54969.49", "qoQComp": null, "yqoQComp": null } ],
    "BAL": [ ... ],
    "CAS": [ ... ]
  }
}
```

**Statement type keys:**

| Key | Statement | Maps to schema table |
|-----|-----------|----------------------|
| `INC` | Income statement | `financials` |
| `BAL` | Balance sheet | `balance_sheets` |
| `CAS` | Cash flow | `cash_flows` |

**Depth observed (varies by ticker):**

| Ticker | `name` used | Annual periods | Interim (quarterly) | Notes |
|--------|-------------|----------------|---------------------|-------|
| HDFC Bank | HDFC Bank | 7 | 9 | |
| ICICI Bank | ICICI Bank | 7 | 9 | |
| State Bank of India | State Bank of India | 7 | 9 | |
| Bajaj Finance | Bajaj Finance | 7 | 9 | |
| SBI Life | SBI Life | **0** | **0** | `financials: null` — use `/historical_stats` fallback |
| Tata Consultancy Services | **TCS** (exact name fails) | 7 | 9 | `"Tata Consultancy Services"` → 404 |
| Infosys | Infosys | 7 | 9 | |
| Hindustan Unilever | Hindustan Unilever | 7 | 9 | |
| Sun Pharmaceutical | **Sun Pharmaceutical** | 7 | 9 | `"Sun Pharma"` → wrong company (SPARC) |
| Tata Motors | Tata Motors | 4 | 7 | NSE symbol `TMCV` (post-demerger), not `TATAMOTORS` |
| Tata Steel | Tata Steel | 8 | 10 | |
| Reliance Industries | Reliance Industries | 7 | 9 | |
| DLF | DLF | 8 | 10 | |
| Bharti Airtel | Bharti Airtel | 8 | 10 | |
| NTPC | NTPC | 8 | 10 | |

**`value` parsing behavior (15,187 string values sampled across tickers):**

| Pattern | Handling |
|---------|----------|
| Positive decimal string (`"81511.14"`) | `float(value)` |
| Negative (`"-48195.19"`) | `float(value)` — leading minus preserved |
| Zero (`"0.00"`) | `float` → `0.0` — **do not treat as missing** |
| `periodType` / `periodLength` rows | Skip — not monetary (`"Months"`, `"12"`, `"0.00"`) |
| Key absent from array | Schema column → `null` |
| `value` key present as JSON `null` | Not observed on monetary rows; treat as `null` if seen |

**Period type / fiscal year / quarter derivation:**

| Schema field | Source | Logic |
|--------------|--------|-------|
| `period_end_date` | `EndDate` | Parse ISO date `"YYYY-MM-DD"` |
| `period_type` | `Type` | `"Annual"` → `'annual'`; `"Interim"` → `'quarterly'` |
| `fiscal_year` | `FiscalYear` | `int(FiscalYear)` — API aligns with Indian FY label |
| `fiscal_quarter` | `EndDate` month | Only when `period_type = 'quarterly'`: Jun→1, Sep→2, Dec→3, Mar→4; else `null` |

`StatementDate` is the **filing/report date**, not period end — do not use for `period_end_date`.

`periodLength` embedded row: `"12"` for annual, `"3"` expected for interim (confirm per row when parsing).

---

### Bank / NBFC / insurance vs industrial — structural differences

**Income statement (`INC`) — keys observed only in banks** (HDFC, ICICI, SBI, Bajaj Finance):

`InterestIncomeBank`, `TotalInterestExpense`, `NetInterestIncome`, `LoanLossProvision`, `NetInterestIncAfterLoanLossProv`, `Non-InterestIncomeBank`, `Non-InterestExpenseBank`, `EquityInAffiliates`

**Income statement — keys observed only in industrials** (Tata Steel, HUL, Tata Motors, Reliance):

`TotalRevenue`, `Revenue`, `CostofRevenueTotal`, `GrossProfit`, `TotalOperatingExpense`, `OtherOperatingExpensesTotal`, `Selling/General/AdminExpensesTotal`, `Depreciation/Amortization`, `Gain(Loss)onSaleofAssets`, `UnusualExpense(Income)`, `DilutionAdjustment`

**Balance sheet (`BAL`) — bank-specific:**

`CashDuefromBanks`, `NetLoans`, `OtherEarningAssetsTotal`, `TotalDeposits`, `TotalShortTermBorrowings`

**Balance sheet — industrial-specific:**

`TotalInventory`, `AccountsReceivable-TradeNet`, `PrepaidExpenses`, `ShortTermInvestments`, `IntangiblesNet`, `CapitalLeaseObligations`, `NotesPayable/ShortTermDebt`, `CurrentPortofLTDebt/CapitalLeases`

**Shared keys (both templates):** `TotalAssets`, `TotalLiabilities`, `TotalEquity`, `TotalDebt`, `LongTermDebt`, `Cash`, `CashEquivalents`, `NetIncome` (INC), `CashfromOperatingActivities` (CAS), etc.

**Wrapper rule:** Map with **coalesce across templates**; never coerce absent bank/industrial rows to zero.

---

### Full `key` inventory (union across probed tickers)

**INC (44 keys):** `CostofRevenueTotal`, `DPS-CommonStockPrimaryIssue`, `Depreciation/Amortization`, `DilutedEPSExcludingExtraOrdItems`, `DilutedNetIncome`, `DilutedNormalizedEPS`, `DilutedWeightedAverageShares`, `DilutionAdjustment`, `EquityInAffiliates`, `Gain(Loss)onSaleofAssets`, `GrossProfit`, `IncomeAvailabletoComExclExtraOrd`, `IncomeAvailabletoComInclExtraOrd`, `InterestInc(Exp)Net-Non-OpTotal`, `InterestIncomeBank`, `LoanLossProvision`, `MinorityInterest`, `NetIncome`, `NetIncomeAfterTaxes`, `NetIncomeBeforeExtraItems`, `NetIncomeBeforeTaxes`, `NetInterestIncAfterLoanLossProv`, `NetInterestIncome`, `Non-InterestExpenseBank`, `Non-InterestIncomeBank`, `OperatingIncome`, `OtherNet`, `OtherOperatingExpensesTotal`, `ProvisionforIncomeTaxes`, `Revenue`, `Selling/General/AdminExpensesTotal`, `TotalAdjustmentstoNetIncome`, `TotalExtraordinaryItems`, `TotalInterestExpense`, `TotalOperatingExpense`, `TotalRevenue`, `UnusualExpense(Income)`, `periodLength`, `periodType`

**BAL (49 keys):** `AccountsPayable`, `AccountsReceivable-TradeNet`, `AccruedExpenses`, `AccumulatedDepreciationTotal`, `AdditionalPaid-InCapital`, `CapitalLeaseObligations`, `Cash`, `CashDuefromBanks`, `CashEquivalents`, `CashandShortTermInvestments`, `CommonStockTotal`, `CurrentPortofLTDebt/CapitalLeases`, `DeferredIncomeTax`, `ESOPDebtGuarantee`, `GoodwillNet`, `IntangiblesNet`, `LongTermDebt`, `LongTermInvestments`, `MinorityInterest`, `NetLoans`, `NoteReceivable-LongTerm`, `NotesPayable/ShortTermDebt`, `OtherAssetsTotal`, `OtherCurrentAssetsTotal`, `OtherCurrentliabilitiesTotal`, `OtherEarningAssetsTotal`, `OtherEquityTotal`, `OtherLiabilitiesTotal`, `OtherLongTermAssetsTotal`, `PrepaidExpenses`, `Property/Plant/EquipmentTotal-Gross`, `Property/Plant/EquipmentTotal-Net`, `RetainedEarnings(AccumulatedDeficit)`, `ShortTermInvestments`, `TangibleBookValueperShareCommonEq`, `TotalAssets`, `TotalCommonSharesOutstanding`, `TotalCurrentAssets`, `TotalCurrentLiabilities`, `TotalDebt`, `TotalDeposits`, `TotalEquity`, `TotalInventory`, `TotalLiabilities`, `TotalLiabilitiesShareholders'Equity`, `TotalLongTermDebt`, `TotalReceivablesNet`, `TotalShortTermBorrowings`, `UnrealizedGain(Loss)`, `periodLength`

**CAS (19 keys):** `CapitalExpenditures`, `CashInterestPaid`, `CashTaxesPaid`, `CashfromFinancingActivities`, `CashfromInvestingActivities`, `CashfromOperatingActivities`, `ChangesinWorkingCapital`, `Depreciation/Depletion`, `FinancingCashFlowItems`, `ForeignExchangeEffects`, `Issuance(Retirement)ofDebtNet`, `Issuance(Retirement)ofStockNet`, `NetChangeinCash`, `NetIncome/StartingLine`, `Non-CashItems`, `OtherInvestingCashFlowItemsTotal`, `TotalCashDividendsPaid`, `periodLength`, `periodType`

---

### `GET /historical_data` — prices

**Params:** `stock_name` (required), `period` (`1m`, `6m`, `1yr`, `3yr`, `5yr`, `10yr`, `max`; default `5yr`), `filter` (`price`, `pe`, `sm`, `evebitda`, `ptb`, `mcs`, `default`)

**Return type:** `dict` with `datasets: list[dict]`

**With `filter=price` (3 tickers probed — Reliance, HDFC Bank, Tata Steel):**

| `metric` | `values` row shape | Notes |
|----------|-------------------|-------|
| `Price` | `["YYYY-MM-DD", "1293.90"]` | **Close only** — both elements strings |
| `DMA50` | `["YYYY-MM-DD", "1335.54"]` | Not in schema — discard or future table |
| `DMA200` | `["YYYY-MM-DD", "1389.13"]` | Not in schema — discard |
| `Volume` | `["YYYY-MM-DD", 16445690, {"delivery": null}]` | Volume is **int**; delivery % optional |

**247 trading days** returned for `period=1yr` (all 3 tickers).

**`filter=default`:** Same dataset structure as `price` (no additional OHLC metrics observed).

**Gaps vs `prices` schema:** No `open`, `high`, `low`, or `adj_close`. Only `close` + `volume` are populate-able.

---

### `GET /corporate_actions`

**Return type:** `dict` with keys: `dividends`, `splits`, `bonus`, `rights`, `board_meetings`

Each section is a **wrapper object**, not a flat list:

```json
{
  "msg": "...",
  "title": "...",
  "header": ["Date", "Record Date", "Yield", "Description"],
  "data": [ ... ]
}
```

**`dividends.data` row (Reliance Industries):**

```json
["05-06-2026", "05-06-2026", "60%", "Outcome of the Board Meeting recommended a dividend of Rs.6.00 per equity share..."]
```

**`bonus.data` row:**

```json
["28-10-2024", "28-10-2024", "1:1"]
```

**HDFC Bank:** sections return wrapper with empty `data` (no recent actions in sample).

**`rights`:** `{title, msg}` only — no tabular `data`.

---

### Name matching strategy

The `/stock` endpoint fuzzy-matches company **names**. Ticker symbols and ISINs are **not** accepted as primary lookup keys.

| Query | Result | Recommended lookup name |
|-------|--------|-------------------------|
| `Tata Consultancy Services` | **404** | `TCS` or `Tata Consultancy` |
| `TCS` / `tcs` | ✓ Tata Consultancy Services | `TCS` |
| `Sun Pharma` | ✗ Sun Pharma **Advanced Research** (wrong co.) | `Sun Pharmaceutical` or `SUNPHARMA` |
| `Sun Pharmaceutical Industries Ltd` | **404** | `Sun Pharmaceutical` |
| `Reliance Industries Limited` | **404** | `Reliance Industries` or `Reliance` |
| `SBI Life` | ✓ SBI Life Insurance Company Ltd | `SBI Life` (profile only; no `/stock` financials) |

**Wrapper recommendation:** Maintain a static `symbol → api_name` resolver table for known tickers. Use `/industry_search?query=...` only as fallback (not yet probed — costs requests). Never assume ticker symbol works as `name`.

---

## Step 2 — Schema Mapping & Gap Analysis

### Derived fields (not from API directly)

| Schema column | Derivation |
|---------------|------------|
| `company_id` | DB-assigned |
| `symbol` | `companyProfile.exchangeCodeNse` (preferred) or derive from resolver table |
| `exchange` | `'NSE'` if `exchangeCodeNse` present, else `'BSE'` |
| `country` | Hardcode `'India'` (not returned explicitly) |
| `period_type` | `Type` → `'annual'` / `'quarterly'` |
| `fiscal_year` | `int(FiscalYear)` |
| `fiscal_quarter` | From `EndDate` month when quarterly; else `null` |
| `currency` | Default `'INR'` — no per-statement currency field observed |
| `non_current_assets` | `total_assets - current_assets` when both present (optional derive) |
| `free_cash_flow` | `operating_cash_flow - abs(capex)` when both present (optional derive) |
| `source` | `'indianapi'` |
| `created_at` / `updated_at` / `ingested_at` | Set at ingestion time |

---

### Table: `companies`

| Schema column | Indian API source | Status |
|---------------|-------------------|--------|
| `company_id` | — | DB-generated |
| `symbol` | `companyProfile.exchangeCodeNse` | ✓ when NSE-listed; **null for BSE-only** (SBI Life: BSE only in sample) |
| `exchange` | derived from NSE/BSE codes | ✓ |
| `country` | — | Default `'India'` |
| `isin` | `companyProfile.isInId` | ✓ all 15 probed |
| `company_name` | `companyName` (top-level) | ✓ |
| `sector` | `companyProfile.mgSector` | **Sparse** — usually `null`; no top-level `sector` field |
| `industry` | `industry` (top-level) or `mgIndustry` | ✓ |
| `shares_outstanding` | `BAL.TotalCommonSharesOutstanding` (latest period) | **Partial** — per-period in statements, not profile; units may be shares cr. |
| `shares_diluted` | `INC.DilutedWeightedAverageShares` | **Partial** — statement row, not profile |
| `listing_date` | — | **GAP: not in API response** |
| `is_active` | — | Default `True` |
| `source` | hardcode `'indianapi'` | ✓ |

---

### Table: `financials`

| Schema column | Indian API `INC` key | Status |
|---------------|---------------------|--------|
| `company_id` | — | DB join |
| `period_end_date` | period `EndDate` | ✓ |
| `period_type` | period `Type` | derived |
| `fiscal_year` / `fiscal_quarter` | period `FiscalYear` + `EndDate` | derived |
| `currency` | — | Default `'INR'` |
| `revenue` | `TotalRevenue` → `Revenue` → `InterestIncomeBank` | ✓ coalesce (bank vs industrial) |
| `cost_of_revenue` | `CostofRevenueTotal` | ✓ industrial only; **null for banks** |
| `gross_profit` | `GrossProfit` | ✓ industrial only; **null for banks** |
| `operating_expenses` | `TotalOperatingExpense` → `Non-InterestExpenseBank` | ✓ template-dependent |
| `operating_profit` | `OperatingIncome` → `NetInterestIncAfterLoanLossProv` | ✓ template-dependent |
| `ebitda` | — | **GAP: no `EBITDA` key** — do not derive without confirmation |
| `ebit` | — | **GAP: no `EBIT` key** |
| `interest_expense` | `TotalInterestExpense` → `InterestInc(Exp)Net-Non-OpTotal` | ✓ partial — bank uses `TotalInterestExpense` |
| `profit_before_tax` | `NetIncomeBeforeTaxes` | ✓ |
| `tax_expense` | `ProvisionforIncomeTaxes` | ✓ |
| `net_profit` | `NetIncome` | ✓ |
| `eps_basic` | — | **GAP: no basic EPS key** (`BasicEPS` absent from union) |
| `eps_diluted` | `DilutedEPSExcludingExtraOrdItems` → `DilutedNormalizedEPS` | ✓ |
| `source` | hardcode `'indianapi'` | ✓ |

**SBI Life:** `/stock` returns `financials: null`. Fallback: `/historical_stats?stats=quarter_results|yoy_results` — different shape (pivot table, not `key`/`value` arrays). **Requires separate parser** in ingestion, not just wrapper field map.

---

### Table: `balance_sheets`

| Schema column | Indian API `BAL` key | Status |
|---------------|---------------------|--------|
| `company_id` | — | DB join |
| `period_end_date` | period `EndDate` | ✓ |
| `period_type` / `fiscal_year` / `fiscal_quarter` | derived | derived |
| `currency` | — | Default `'INR'` |
| `total_assets` | `TotalAssets` | ✓ |
| `current_assets` | `TotalCurrentAssets` | ✓ industrial; **often absent for banks** |
| `non_current_assets` | — | **GAP** — derive `total_assets - current_assets` or leave null |
| `cash_and_equivalents` | `CashandShortTermInvestments` → `Cash` + `CashEquivalents` | ✓ coalesce |
| `inventory` | `TotalInventory` | ✓ industrial only |
| `receivables` | `TotalReceivablesNet` → `AccountsReceivable-TradeNet` | ✓ |
| `total_liabilities` | `TotalLiabilities` | ✓ |
| `current_liabilities` | `TotalCurrentLiabilities` | ✓ industrial; sparse for banks |
| `non_current_liabilities` | — | **GAP** — derive or leave null |
| `total_debt` | `TotalDebt` | ✓ |
| `short_term_debt` | `NotesPayable/ShortTermDebt` → `TotalShortTermBorrowings` | ✓ partial |
| `long_term_debt` | `LongTermDebt` → `TotalLongTermDebt` | ✓ |
| `total_equity` | `TotalEquity` | ✓ |
| `retained_earnings` | `RetainedEarnings(AccumulatedDeficit)` | ✓ |
| `source` | hardcode `'indianapi'` | ✓ |

---

### Table: `cash_flows`

| Schema column | Indian API `CAS` key | Status |
|---------------|---------------------|--------|
| `company_id` | — | DB join |
| `period_end_date` | period `EndDate` | ✓ |
| `period_type` / `fiscal_year` / `fiscal_quarter` | derived | derived |
| `currency` | — | Default `'INR'` |
| `operating_cash_flow` | `CashfromOperatingActivities` | ✓ |
| `investing_cash_flow` | `CashfromInvestingActivities` | ✓ |
| `financing_cash_flow` | `CashfromFinancingActivities` | ✓ |
| `net_cash_flow` | `NetChangeinCash` | ✓ |
| `capex` | `CapitalExpenditures` | ✓ (typically negative string) |
| `free_cash_flow` | — | **GAP** — derive `OCF - abs(CapEx)` or leave null |
| `source` | hardcode `'indianapi'` | ✓ |

---

### Table: `prices`

| Schema column | Indian API source | Status |
|---------------|-------------------|--------|
| `company_id` | — | DB join |
| `trade_date` | `datasets[Price].values[*][0]` | ✓ ISO date string |
| `open` | — | **GAP: not provided** |
| `high` | — | **GAP** (`stockDetailsReusableData.high` is spot, not historical) |
| `low` | — | **GAP** |
| `close` | `datasets[Price].values[*][1]` | ✓ parse string → float |
| `volume` | `datasets[Volume].values[*][1]` | ✓ int |
| `adj_close` | — | **GAP: not provided** |
| `source` | hardcode `'indianapi'` | ✓ |

---

### Table: `corporate_actions`

| Schema column | Indian API source | Status |
|---------------|-------------------|--------|
| `company_id` | — | DB join |
| `action_date` | `data[*][0]` (DD-MM-YYYY) | ✓ parse date |
| `action_type` | section key | `'dividend'` / `'split'` / `'bonus'` / `'other'` (board_meetings, rights) |
| `ex_date` | `dividends data[*][0]` | **Partial** — same as action_date in sample; splits/bonus use col 0 |
| `record_date` | `data[*][1]` | ✓ when present |
| `payment_date` | — | **GAP** |
| `currency` | — | Default `'INR'` |
| `amount` | dividend description text | **Partial** — per-share amount embedded in text (`Rs.6.00`), not structured |
| `ratio_from` / `ratio_to` | `bonus data[*][2]` e.g. `"1:1"` | **Partial** — parse ratio string; splits format not confirmed |
| `description` | `data[*][3]` (dividends) | ✓ |
| `source` | hardcode `'indianapi'` | ✓ |

`board_meetings` and `rights` do not map cleanly to split/bonus/dividend schema — store as `'other'` or skip.

---

## API Fields With No Schema Home

Recommend **discard at wrapper boundary** unless a future table is added:

| API field / endpoint output | Notes |
|----------------------------|-------|
| `keyMetrics` (margins, valuation, growth, etc.) | TTM ratios — future `key_metrics` table |
| `analystView`, `recosBar`, `riskMeter` | Analyst sentiment |
| `shareholding` | Promoter/FII/MF breakdown — future table |
| `stockTechnicalData` | Technical indicators |
| `peerCompanyList` | Peer comparison with P/E, market cap |
| `qoQComp`, `yqoQComp` on line items | QoQ/YoY % change per row |
| `stockDetailsReusableData` | Spot quote snapshot (price, mcap, day high/low) |
| `recentNews` | Out of scope |
| `futureExpiryDates`, `futureOverviewData` | F&O data |
| Historical `DMA50`, `DMA200` | Moving averages |
| Volume `delivery` % | Useful for analysis, not in schema |
| `/historical_stats` ratios, shareholding | Separate tabular format |

---

## Parsing Logic (for wrapper implementation)

### 1. String → float

```python
SKIP_KEYS = {"periodType", "periodLength"}

def parse_amount(value: str | None, key: str) -> float | None:
    if key in SKIP_KEYS:
        return None
    if value is None:
        return None
    value = value.strip()
    if value == "" or value == "-":
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None  # log unexpected tokens
```

- **Never** coerce parse failures or absent keys to `0.0`.
- Negative values arrive as `"-48195.19"` — standard `float()` handles them.

### 2. Statement row → column dict

```python
def rows_to_dict(rows: list[dict]) -> dict[str, float | None]:
    return {
        row["key"]: parse_amount(row.get("value"), row["key"])
        for row in rows
        if row.get("key") not in SKIP_KEYS
    }
```

Then apply the mapping tables above with `coalesce(row.get(k) for k in candidates)`.

### 3. Period → schema row

```python
def period_metadata(period: dict) -> dict:
    end = date.fromisoformat(period["EndDate"])
    ptype = "annual" if period["Type"] == "Annual" else "quarterly"
    fy = int(period["FiscalYear"])
    fq = {6: 1, 9: 2, 12: 3, 3: 4}.get(end.month) if ptype == "quarterly" else None
    return {
        "period_end_date": end,
        "period_type": ptype,
        "fiscal_year": fy,
        "fiscal_quarter": fq,
    }
```

### 4. Name resolution

```python
# Preferred: static map built from probe results
API_NAME_BY_SYMBOL = {
    "TCS": "TCS",
    "SUNPHARMA": "Sun Pharmaceutical",
    "SBILIFE": "SBI Life",
    # ...
}

def resolve_api_name(symbol: str, company_name_hint: str | None = None) -> str:
    if symbol in API_NAME_BY_SYMBOL:
        return API_NAME_BY_SYMBOL[symbol]
    return company_name_hint or symbol  # last resort — may 404
```

### 5. Price history flatten

```python
# Match datasets by metric name
price_ds = next(d for d in resp["datasets"] if d["metric"] == "Price")
vol_ds   = next(d for d in resp["datasets"] if d["metric"] == "Volume")
vol_by_date = {row[0]: row[1] for row in vol_ds["values"]}
for date_str, close_str in price_ds["values"]:
    yield {"trade_date": date_str, "close": float(close_str), "volume": vol_by_date.get(date_str)}
```

### 6. Corporate action date parse

Dividend/split dates use **`DD-MM-YYYY`** (not ISO). Parse with `datetime.strptime(s, "%d-%m-%Y").date()`.

---

## Units & Currency

| Data | Unit / currency | Notes |
|------|-----------------|-------|
| Statement amounts | **INR crores** | Confirmed via Bajaj Finance revenue cross-check |
| EPS keys | Per-share INR | `DilutedEPSExcludingExtraOrdItems` |
| Price `close` | INR per share | String in API |
| Volume | Shares | Integer |
| `currentPrice` | INR per share | Strings per exchange |
| Statement `currency` column | **INR** | No USD reporting observed (unlike yfinance INFY) |

---

## Known Weak Spots (summary)

Priority issues for wrapper (null-preserving) and ingestion:

1. **Name-based lookup** — exact legal names often 404; symbols work inconsistently; maintain resolver table.
2. **SBI Life (insurance)** — `/stock` financials are `null`; need `/historical_stats` alternate parser.
3. **Sun Pharma** — `"Sun Pharma"` resolves to wrong company; use `"Sun Pharmaceutical"`.
4. **TCS** — `"Tata Consultancy Services"` 404; use `"TCS"`.
5. **Tata Motors** — post-demerger NSE symbol is `TMCV`, not `TATAMOTORS`.
6. **No OHLC** — only close + volume from `/historical_data`; `open`/`high`/`low`/`adj_close` stay null.
7. **EBIT / EBITDA / basic EPS** — keys absent; columns stay null.
8. **Bank vs industrial templates** — many schema columns legitimately null per template.
9. **`listing_date`** — not available from API.
10. **`sector`** — `mgSector` usually null; only `industry` reliable.
11. **Corporate actions** — unstructured dividend amounts; board meetings/rights don't fit schema cleanly.
12. **`fiscalPeriodNumber`** — always 0; useless for quarter detection.
13. **BSE-only listings** — `exchangeCodeNse` null (SBI Life); schema needs BSE symbol handling.
14. **Request budget** — 500/month; wrapper must count and log every call.

---

## Wrapper Design Notes (for Step 3)

When `src/api/indianapi/client.py` is built:

1. **No retry logic, no DB writes** — fetch + parse only.
2. **Request counter** — module-level counter + structured log line per call (`path`, `params`, cumulative count).
3. Load API key from `INDIAN_API_KEY` env var; base URL constant `https://stock.indianapi.in`.
4. Functions: `fetch_company(name)`, `fetch_financials(name)` (parsed rows), `fetch_prices(name, period, filter)`, `fetch_corporate_actions(name)`.
5. Flatten `stockFinancialMap` at parse boundary; skip `periodType`/`periodLength` rows.
6. Use `coalesce` mappings for bank/industrial templates.
7. Do **not** build wrappers for out-of-scope endpoints.
8. Consider caching `/stock` response — profile + financials + `stockFinancialData` are redundant copies.

---

## Re-running This Investigation

```bash
.venv/bin/python scripts/investigate_indianapi.py
# Output: scripts/indianapi_probe_output.json
# WARNING: each run costs ~23+ API requests
```

Additional targeted probes (only when budget allows):

- `/statement` vs `/stock` financials equivalence
- `/industry_search` as name-resolution fallback
- SBI Life `/historical_stats` full shape for insurance parser design
