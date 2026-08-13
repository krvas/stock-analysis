# Indian Stock Analysis Platform

Python-based data platform for NSE/BSE and US equities. Ingests market and financial data into **DuckDB**, and serves interactive HTML views via **FastAPI + Jinja2** (with room for HTMX-backed screening).

## Tech Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3.12 |
| Web | FastAPI, Jinja2, uvicorn |
| Analytics DB | DuckDB |
| DataFrames | pandas |
| Raw storage | Parquet (PyArrow) |
| US filings | edgartools (SEC EDGAR) |
| Market/financial data | IndianAPI, Alpha Vantage, Finnhub (finfetch planned) |
| Resilience | tenacity (retries) |

## Project Structure

```
project_root/
├── data/
│   ├── raw/              # Cached API / filing responses
│   ├── processed/        # Intermediate artifacts
│   └── duckdb/           # indian_stocks.duckdb
├── src/
│   ├── api/              # Vendor clients (IndianAPI, Alpha Vantage, Finnhub, edgartools)
│   ├── ingestion/        # Load API data into DuckDB
│   ├── database/         # Schema, DatabaseManager
│   ├── models/           # Payload builders / view models
│   ├── pipelines/        # CLI orchestration (ingest, etc.)
│   ├── analytics/        # Screeners, factor SQL (planned)
│   ├── web/              # FastAPI app + routes
│   ├── templates/        # Jinja2 HTML templates
│   ├── static/           # Shared CSS / JS
│   └── utils/
├── notebooks/
├── tests/
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# Create virtual environment (Python 3.12)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize DuckDB schema
python -m src.database.init_schema

# Run the web app
uvicorn src.web.app:app --reload
```

Then open:

- Statements: `http://127.0.0.1:8000/statements/AAPL`
- Optional query params: `statement_type=income|balance|cashflow`, `period=annual|quarterly`, `num_periods=10`
- Screener placeholder: `http://127.0.0.1:8000/screener`
- API docs: `http://127.0.0.1:8000/docs`

SEC identity for edgartools uses `EDGAR_IDENTITY` from `.env`.

### DatabaseManager

```python
from src.database import DatabaseManager
import pandas as pd

with DatabaseManager() as db:
    db.initialize_schema()
    db.upsert_dataframe("companies", companies_df)  # auto-assigns company_id
    db.upsert_dataframe("prices", prices_df)        # INSERT OR REPLACE on PK
    db.load_parquet("prices", "data/processed/reliance_prices.parquet")
    latest = db.max_trade_date(company_id=1)  # incremental price updates
```

## DuckDB Schema

| Table | Purpose | Primary key |
|-------|---------|-------------|
| `companies` | Master list of NSE/BSE symbols | `company_id` (unique: `symbol`, `exchange`) |
| `prices` | Daily OHLCV | `(company_id, trade_date)` |
| `financials` | P&L (annual + quarterly) | `(company_id, period_end_date, period_type)` |
| `balance_sheets` | Assets / liabilities / equity | `(company_id, period_end_date, period_type)` |
| `cash_flows` | Operating / investing / financing CF | `(company_id, period_end_date, period_type)` |
| `corporate_actions` | Splits / bonuses / dividends / etc. | `(company_id, action_date, action_type)` |

`period_type` on `financials`, `balance_sheets`, and `cash_flows` is `'annual'` or `'quarterly'`.

## Data Layout (Parquet)

Raw files are organized under `data/raw/`:

```
data/raw/
├── companies/
├── prices/{exchange}/{symbol}/
├── financials/
├── balance_sheets/
├── cash_flows/
└── corporate_actions/
```

## Roadmap

- [x] Project structure and DuckDB schema
- [x] DatabaseManager class
- [x] IndianAPI / Alpha Vantage / Finnhub clients
- [x] edgartools statement fetch + FastAPI/Jinja statement viewer
- [ ] Implement caching for edgartools
- [ ] Add new processed views
- [ ] Change the statement parameter to a toggle (like level of detail)
- [ ] Ingestion pipelines (companies, prices, financials)
- [ ] Cross-company screener (HTMX + DuckDB / `src/analytics`)
- [ ] CLI (`init`, `ingest`, `update-prices`, `update-financials`, `screen`)
- [ ] Sample screener (ROE > 15%, D/E < 0.5, 3Y revenue growth)

## License

Private / educational use. Verify data vendor terms before production use.
