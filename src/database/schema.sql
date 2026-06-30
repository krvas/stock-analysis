-- =============================================================================
-- Indian Stock Analysis Platform — DuckDB Schema
-- =============================================================================
--   companies            — master dimension (NSE / BSE)
--   prices               — daily OHLCV
--   financials           — P&L (annual + quarterly)
--   balance_sheets       — assets / liabilities / equity
--   cash_flows           — cash flow statement
--   corporate_actions    — splits / bonuses / dividends / etc.
-- =============================================================================

CREATE TABLE IF NOT EXISTS companies (
    company_id          INTEGER PRIMARY KEY,
    symbol              VARCHAR NOT NULL,
    exchange            VARCHAR NOT NULL,
    country             VARCHAR,
    isin                VARCHAR,
    company_name        VARCHAR NOT NULL,
    sector              VARCHAR,
    industry            VARCHAR,
    shares_outstanding  BIGINT,
    shares_diluted      BIGINT,
    listing_date        DATE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    source              VARCHAR NOT NULL DEFAULT 'finfetch',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, exchange)
);

CREATE TABLE IF NOT EXISTS prices (
    company_id        INTEGER NOT NULL,
    trade_date        DATE NOT NULL,
    open              DOUBLE,
    high              DOUBLE,
    low               DOUBLE,
    close             DOUBLE NOT NULL,
    volume            BIGINT,
    adj_close         DOUBLE,
    source            VARCHAR NOT NULL DEFAULT 'finfetch',
    ingested_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, trade_date),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS financials (
    company_id            INTEGER NOT NULL,
    period_end_date       DATE NOT NULL,
    period_type           VARCHAR NOT NULL, -- 'annual' | 'quarterly'
    fiscal_year           INTEGER NOT NULL,
    fiscal_quarter        INTEGER,
    currency              VARCHAR NOT NULL DEFAULT 'INR',
    revenue               DOUBLE,
    cost_of_revenue       DOUBLE,
    gross_profit          DOUBLE,
    operating_expenses    DOUBLE,
    operating_profit      DOUBLE,
    ebitda                DOUBLE,
    ebit                  DOUBLE,
    interest_expense      DOUBLE,
    profit_before_tax     DOUBLE,
    tax_expense           DOUBLE,
    net_profit            DOUBLE,
    eps_basic             DOUBLE,
    eps_diluted           DOUBLE,
    source                VARCHAR NOT NULL DEFAULT 'finfetch',
    ingested_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_end_date, period_type),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS balance_sheets (
    company_id              INTEGER NOT NULL,
    period_end_date         DATE NOT NULL,
    period_type             VARCHAR NOT NULL,
    fiscal_year             INTEGER NOT NULL,
    fiscal_quarter          INTEGER,
    currency                VARCHAR NOT NULL DEFAULT 'INR',
    total_assets            DOUBLE,
    current_assets          DOUBLE,
    non_current_assets      DOUBLE,
    cash_and_equivalents    DOUBLE,
    inventory               DOUBLE,
    receivables             DOUBLE,
    total_liabilities       DOUBLE,
    current_liabilities     DOUBLE,
    non_current_liabilities DOUBLE,
    total_debt              DOUBLE,
    short_term_debt         DOUBLE,
    long_term_debt          DOUBLE,
    total_equity            DOUBLE,
    retained_earnings       DOUBLE,
    source                  VARCHAR NOT NULL DEFAULT 'finfetch',
    ingested_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_end_date, period_type),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS cash_flows (
    company_id              INTEGER NOT NULL,
    period_end_date         DATE NOT NULL,
    period_type             VARCHAR NOT NULL,
    fiscal_year             INTEGER NOT NULL,
    fiscal_quarter          INTEGER,
    currency                VARCHAR NOT NULL DEFAULT 'INR',
    operating_cash_flow     DOUBLE,
    investing_cash_flow     DOUBLE,
    financing_cash_flow     DOUBLE,
    net_cash_flow           DOUBLE,
    capex                   DOUBLE,
    free_cash_flow          DOUBLE,
    source                  VARCHAR NOT NULL DEFAULT 'finfetch',
    ingested_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, period_end_date, period_type),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    company_id            INTEGER NOT NULL,
    action_date           DATE NOT NULL,
    action_type           VARCHAR NOT NULL, -- 'split' | 'bonus' | 'dividend' | 'buyback' | 'spinoff' | 'other'
    ex_date               DATE,
    record_date           DATE,
    payment_date          DATE,
    currency              VARCHAR NOT NULL DEFAULT 'INR',
    amount                DOUBLE, -- e.g., dividend per share; optional for non-cash actions
    ratio_from            INTEGER, -- e.g., split 1:2 => ratio_from=1
    ratio_to              INTEGER, -- e.g., split 1:2 => ratio_to=2
    description           VARCHAR,
    source                VARCHAR NOT NULL DEFAULT 'finfetch',
    ingested_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, action_date, action_type),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);
