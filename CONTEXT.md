# Stock Analysis Wizard

A step-by-step wizard that walks one human through a single public equity, from understanding the business to valuing it, so they can decide whether to buy it.

## Language

### Navigation and settings

**Setting**:
A display choice the human makes (e.g. period type, view, basis) that changes what a page shows but never changes saved analysis. A capitalize checkbox or a maintenance % is an input, not a Setting.
_Avoid_: Toggle, control, preference (prefs are saved analysis)

**Global Setting**:
A Setting that applies to every sub-page unless a sub-page declares it cannot honour it.

**Sub-page Setting**:
A Setting that applies only to the sub-pages that declare it; one Setting may be declared by several sub-pages (e.g. basis).

**View**:
How much detail a sub-page shows: summary, standard or detailed. Each sub-page interprets it in its own terms: rows on a statement, verbosity of an AI answer.
_Avoid_: Level, granularity, answer detail

### Adjustments

**Owner Earnings**:
The cash a business could pay its owners each year, before tax and excluding exceptional items, after setting aside maintenance capex and maintenance working capital.
_Avoid_: Free cash flow, OE (in prose)

**Gross Assets in Use**:
The part of the company's assets that is productive today; assets under construction or idle are excluded.
_Avoid_: Operating assets, capital employed

**Net Assets in Use**:
Gross Assets in Use minus the liability lines the human chose to net out (e.g. payables). It is the ROCE denominator.
_Avoid_: Capital employed

### Business quality

**Moat**:
A durable reason competitors cannot take this company's returns away. The wizard judges exactly six: Low Cost, Legal / Patent, Brand, Complexity, Risk, Attention to Detail.
_Avoid_: Competitive advantage (too broad), edge

**Moat Verdict**:
The grade a Moat gets for one company: None, Weak or Strong.
_Avoid_: Score, rating

**Low Cost**:
The company can produce or deliver at a structurally lower cost than rivals, from any source (scale, labour, location, process). Scale economics shared is one form of it, not the definition.
_Avoid_: Economies of scale (only one source)

**Legal / Patent**:
Protection granted by law (patents, licences, regulation). It can be infringed and it expires, so it is never permanent even when Strong.
_Avoid_: IP moat

**Brand**:
Customers prefer the name itself; strongest for frequent, low-value purchases.

**Complexity**:
Anything that makes the business hard to replicate: a product or process that is hard to copy, or an integration that is costly for the customer to replace.

**Risk**:
The risk a customer takes by buying from an unbranded new entrant instead of the incumbent (safety, reliability, failure cost), which keeps them with the incumbent.
_Avoid_: Safety (only one kind of risk)

**Attention to Detail**:
Many small operating advantages that add up to something rivals cannot match by copying any single one.

**ROCE**:
Owner Earnings divided by the average of opening and closing Net Assets in Use for the period.
_Avoid_: ROIC, return on assets

**After-tax Owner Earnings**:
Owner Earnings minus the reported income tax expense of the same period (no computed tax rate).

**Retained Earnings**:
After-tax Owner Earnings minus Distributions for a period: what the business kept to reinvest, counting growth spending that adjustments capitalized (e.g. brand advertising). Not the balance-sheet Retained Earnings line.
_Avoid_: Reinvested earnings, retained profits

**Retained Earnings Test**:
Change in market cap over N years divided by the sum of Retained Earnings over the same years: value created per unit of currency retained.
_Avoid_: Value per rupee retained, one-dollar test

### Valuation

**Distributions**:
Cash returned to shareholders in a year: dividends plus net buybacks (repurchases minus stock issued). A buyback is treated as a dividend.
_Avoid_: Payout, shareholder yield (that is Distributions ÷ market cap)

**Neff Ratio**:
(Owner Earnings growth % + Distributions yield %) ÷ (market cap ÷ Owner Earnings), on whole-company, pre-tax Owner Earnings rather than per-share figures.
_Avoid_: Total return ratio, PEGY

**Target Neff**:
The Neff Ratio the human requires before buying; defaults to 1.5.
_Avoid_: Hurdle

**Reinvestment Rate**:
Retained Earnings as a share of (pre-tax) Owner Earnings, so that ROCE × Reinvestment Rate stays on one tax basis.

**Reinvestment-implied Growth**:
ROCE × Reinvestment Rate: how fast earnings can grow from capital the business keeps.

**Scenario**:
One of the human's bear, base or bull views of the company in five years.
_Avoid_: Case, model
