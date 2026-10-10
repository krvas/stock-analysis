# Open question: are dimensional rows a parent's breakdown?

Status: **open question, not scheduled.** Nothing decided, nothing built.
Owner: Krish (single user, local app).
Related: `specs/vision.md` ("Balance sheet size"), `specs/STATE.md` §4
(views as projections, `get_row_id`, `calc_edges`, `dimension_key`,
`is_breakdown`).
Consumers affected: Balance Sheet Size (wizard business-understanding page),
Assets in Use (wizard adjustments page, `specs/features-grilled/assets-in-use.md`),
`/statements` standard and detailed views.

## 1. Background

The vision for Balance Sheet Size: show the X largest items on each side of
the balance sheet at summary level, and break them down when the user asks for
more granularity. The plan was to reuse the statement views (STATE §4:
summary = non-dimensional rows, standard = `in_standard`, detailed = all):

- an **item** = a summary-view row with no calc children in that period;
- in standard or detailed, dimensional rows (`concept|Axis=member`, see
  `get_row_id`) are drawn as sub-rectangles under their parent row.

Because of the data problems below, the demo uses the **summary view only**
(the page takes no view parameter). This file records why, so that the
breakdown step can be decided later.

**Assets in Use** has the same need and the same v1 workaround. It lists
summary-view asset leaves (each with a "% in use") and liability leaves (each
with a "net out" checkbox), using Balance Sheet Size's item definition. The
user wants it in the detailed view eventually: assets that are not in use yet
(construction in progress, a ramping plant) usually sit *below* summary level,
inside PP&E. A per-row "% in use" can only exclude them once those rows are
listed. So whatever breakdown rule this file settles must also give Assets in
Use a set of rows that partition each leaf without double counting, or the
in-use % would apply twice.

## 2. Verified data facts

Checked on the latest annual balance sheet of each cached ticker (AAPL, MU,
SNDK; edgartools cache).

Every extra row that standard or detailed adds over summary is a dimensional
row of a summary concept. Standard adds very few: SNDK 2
(`AccountsPayableCurrent` × `RelatedPartyTransactionsByRelatedPartyAxis`),
AAPL 1 (`CommercialPaper` × `ShortTermDebtTypeAxis`), MU 0. Detailed adds the
rest.

Ratio = Σ dimensional rows ÷ parent value.

| Parent | Axis (rows) | Ratio | Note |
| --- | --- | --- | --- |
| SNDK `PropertyPlantAndEquipmentNet` | `StatementGeographicalAxis` (5) | 1.00 | Clean single partition. |
| SNDK `StockholdersEquity` | `StatementEquityComponentsAxis` (8) | 0.98 | Near-partition. |
| MU `Goodwill` | `StatementBusinessSegmentsAxis` (4) | 1.00 | Clean single partition. |
| AAPL `MarketableSecuritiesCurrent` | `FairValueByFairValueHierarchyLevelAxis` (2); same × `FinancialInstrumentAxis` (10) | 1.00; 1.00 | Overlapping partitions: drawing both double counts. |
| AAPL `CashAndCashEquivalentsAtCarryingValue` | `FinancialInstrumentAxis` (1); `FairValueByFairValueHierarchyLevelAxis` (2); both axes (10) | 0.79; 0.21; 0.21 | Partial breakdowns on different axes. |
| MU `CashAndCashEquivalentsAtCarryingValue` | `FinancialInstrumentAxis` (1); FairValue × FinancialInstrument (6) | 0.69; 0.31 | Partial. |
| SNDK `OtherAssetsNoncurrent` / `Assets` / `AssetsCurrent` / `LiabilitiesCurrent` / `Liabilities` / `StockholdersEquity` | `EquityMethodInvestmentNonconsolidatedInvesteeAxis` (1 each) | 4.19 / 0.33 / 0.12 / 0.54 / 0.93 / 0.07 | The investee's own balance-sheet figures, not a breakdown of the filer's line. Some hang off subtotals. |
| SNDK `AccountsPayableCurrent` | `RelatedPartyTransactionsByRelatedPartyAxis` (2); plus a 2-axis combo row | 1.00; 0.33 | Partition plus an extra multi-axis row. |

Conclusion: "the dimensional rows under a row are its breakdown" is **false
in general**. The rule fails in four ways:

1. **Overlapping partitions:** several axis sets each sum to the parent.
2. **Partial partitions:** the dimensional rows cover only part of the parent.
3. **Rows that are not breakdowns at all,** e.g. investee data
   (ratio 4.19 > 1).
4. **Multi-axis combinations** mixed with single-axis rows on the same parent.

## 3. Open questions

None of these is decided.

- **Q1. Which axes count as breakdowns?** An allow-list (geography, segments,
  equity components, …) or a deny-list (e.g.
  `EquityMethodInvestmentNonconsolidatedInvesteeAxis`)?
- **Q2. When several partitions sum to the parent, which one is shown?**
  Fewest rows, a fixed axis priority, or a user choice?
- **Q3. What happens to a partial partition?** Show it with a residual
  "Other" rectangle, or drop it?
- **Q4. Single-axis only, or multi-axis too?**
- **Q5. Where does the rule live?** In the `Statement` model or projection,
  shared by the `/statements` views, or only in consumers like Balance Sheet
  Size?
- **Q6. Can calc-linkbase dimension info disambiguate?** Can `dimension_key`
  or `is_breakdown` from the aligned raw items (STATE §4) tell the cases in
  §2 apart?
- **Q8. For Assets in Use, how does a saved "% in use" behave when the view
  changes?** If a % is saved on a summary leaf and its breakdown rows appear
  later, does the leaf's % apply to the remainder, get replaced by per-row
  %s, or get carried down to each child?
- **Q7. Does this change how `/statements` presents standard and detailed
  today?** Those views already list these rows under their parents, so
  overlapping or non-breakdown rows can read like children there too.

## 4. Possible directions

Listed for discussion only; this file makes no recommendation.

- Keep Balance Sheet Size at summary level permanently, and use calc children
  as the only drill-down.
- Accept a parent's dimensional rows as a breakdown only when one single-axis
  set sums to the parent within a tolerance; otherwise show no breakdown.
- Curate an axis allow-list or deny-list, applied in one shared place.
- Show partial partitions with an explicit residual "Other" rectangle.
- Let the user pick the axis per item when several partitions exist.
- Derive breakdown membership from `is_breakdown` / `dimension_key` if Q6
  shows they are reliable.

## 5. Data checks still needed

- Other tickers beyond AAPL, MU and SNDK.
- Other periods: earlier annual filings and quarterly filings.
- Income and cash-flow statements (segment revenue, D&A note breakdowns).
- Whether `is_breakdown` / `dimension_key` separate the four failure cases
  in §2 (feeds Q6).
