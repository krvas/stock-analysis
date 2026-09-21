-- Wizard / edgartools analysis preferences (separate from core ingestion schema).

CREATE TABLE IF NOT EXISTS adjustment_preferences (
    adjustment_id     VARCHAR PRIMARY KEY,      -- uuid
    ticker            VARCHAR NOT NULL,
    exchange          VARCHAR NOT NULL,
    statement         VARCHAR NOT NULL,          -- 'BS' | 'CF' | 'PL'
    adjustment_type   VARCHAR NOT NULL,          -- 'opex_to_capex' | 'maintenance_capex' | 'assets_in_use'
    base_concept      VARCHAR NOT NULL,          -- statement line item the adjustment applies to
    base_concept_statement         VARCHAR NOT NULL,          -- 'BS' | 'CF' | 'PL'
    value              DOUBLE NOT NULL,           -- years (opex_to_capex) or % (maintenance_capex, assets_in_use)
    consolidated_ids   VARCHAR,                   -- comma-joined CSV ids this preference satisfies (traceability)
    updated_at         TIMESTAMP NOT NULL,

    UNIQUE (ticker, exchange, adjustment_type, base_concept)
);
