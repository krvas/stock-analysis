# Indian Stock Analysis Platform

Python-based data platform for NSE and BSE listed companies. Ingests market and financial data via **finfetch**, stores raw responses as **Parquet**, and loads normalized tables into **DuckDB** for screening, factor research, backtesting, and ML workflows.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3.12 |
| Analytics DB | DuckDB |
| DataFrames | pandas |
| Raw storage | Parquet (PyArrow) |
| Market/financial data | finfetch |
| Resilience | tenacity (retries) |

## Project Structure

```
project_root/
├── data/
│   ├── raw/              # API responses as Parquet (partitioned by dataset)
│   ├── processed/        # Cleaned Parquet before DuckDB load
│   └── duckdb/           # indian_stocks.duckdb
├── src/
│   ├── api/              # finfetch wrapper clients
│   ├── ingestion/        # Fetch → Parquet → DuckDB loaders
│   ├── database/         # Schema, DatabaseManager
│   ├── models/           # Pydantic/dataclass models
│   ├── pipelines/        # Orchestration (full / incremental)
│   ├── utils/            # Logging, retry decorators
│   └── analytics/        # Screeners, factor SQL
├── notebooks/
├── tests/
├── requirements.txt
└── README.md
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

## Quick Start

```bash
# Create virtual environment (Python 3.12)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize DuckDB schema
python -m src.database.init_schema
```

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
- [ ] finfetch API wrappers
- [ ] Ingestion pipelines (companies, prices, financials)
- [ ] CLI (`init`, `ingest`, `update-prices`, `update-financials`, `screen`)
- [ ] Sample screener (ROE > 15%, D/E < 0.5, 3Y revenue growth)

## License

Private / educational use. Verify data vendor terms before production use.
