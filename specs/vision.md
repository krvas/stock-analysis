
## Page 1 - Business Understanding

### One line answers
What industry do they operate in?
What is the structure of the industry?
Who are their biggest partners (e.g. manufacturers, distributors, customers, etc.)?
What is their core competency?
What part of the value chain / risk do they own? What part of the value chain / risk do they not own?
Who are their competitors?

Is it a commodity business?

### Balance sheet size
X largest items on both asset and liability side of balance sheet (X is an adjustable parameter)
With SEC Edgar, multiple levels of granularity are available. The X largest items should be of the summary level, and if higher granularity is demanded, those items should be broken down.

Also check if they are using float

### Fund flow View

### Revenue drivers

## Page 2 - Adjustments

### Look through earnings for holding companies
This might also apply to non holding companies, if they have substantial shares in other companies
Find out a way to evaluate and automate this
The final output needs to be some sort of dashboard that will give the human the option to "look through" into subsidiaries' balance sheets.

<details>
For version 1, just pull the 13F filings, show this to the user and the user should have the ability to click a link to go to the page of the held company
</details>

### Opex to Capex Adjustments
Check if we should capitalise R&D and/or advertising

<details>
First, the user should be shown the opex of the company.
The user then selects what opex needs to be capitalised, and for how many years.
That gets sent to the backend. Statements are converted to pandas dataframe, and the adjustments are applied.
The adjustments themselves should be stored, not the results of the adjustments, so that if the underlying data is updated, the final table is also updated.
</details>

**Deliverables**:
- New rows in the balance sheet (2 per converted opex) - of gross & net assets
- New rows in the P&L to depreciate the new assets

### Owner's Earnings Calculations
Page contains pre-tax, pre-exceptional item Net profit
Page also contains depreciation & amortization broken down by asset. There should also be a row for the human to enter either percentages or values that denote the average maintenance capex.
Important information to be pulled from annual report, like how much they have invested for growth, what their fixed assets are, etc. 
If they explicitly mention maintenance expenses, those should be pulled here too.

**Deliverables**:
- Three new rows in the CF statement - maintenance capex, maintenance WC and Owner Earnings

### Assets in-use
Not necessarily an adjustment, but an intermediate calculation. This page should attempt to compute which part of the assets are actually in use.

**Deliverables**:
- One new (intermediate) row in the balance sheet, representing assets in-use 

## Page 3 - Business Quality

### Moats
From the list of 6 moats, which ones apply here

### ROCE computation
Post adjustments
- Owner Earnings
- Opex to Capex
- Assets in use

Also include value created per rupee of retained earning

### Common Causes of Business Failure
Checklist from Don Keough's book. Should be implemented after I have read it. 

## Page 4 - Management Quality

Check the management compensation structure - salaries / stock options
What are the terms of the stock options?
When have buybacks been issued? What has management said about that versus investment opportunities and dividends?


## Page 5 - Valuation

### Growth estimation
A dashboard that helps the user figure out how the company will grow. Still figuring this out.

### Neff Ratio
This page contains both, calculation of Neff and calculation of expected growth given Neff

### Bond as a Business
This will give the PE ratio, and compare 1/PE to the AAA bond yeild in the country.

## Page 6 - Red Flags

This is a page with many small checks that can be automated. The user should have the option to override a small check, saying it is not applicable.

Examples:
If CFO > Net income
If Owner's Earnings < Reported Earnings

## Further Scope (kept out of v1)

### Dupont decomposition
To see where growth is coming from
Can do this for competitors as well, to see if there is scope for efficiency gain

### Risks & Moat Widening duty
This will have to be implemented after seeing some data
I think there should be two separate (but connected) sub-pages, one focusing on risks and the other that lists the risks, but also mentions what management has said about them.